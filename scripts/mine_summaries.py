#!/usr/bin/env python3
"""Mine linguistic summaries over the arrivals table (UC-023; `make mine`).

    uv run python scripts/mine_summaries.py                      # data/processed -> summaries
    uv run python scripts/mine_summaries.py --arrivals a.parquet --out s.parquet

For each segment (network; network per study half) and each summarizer word of
`arrival_delay_minutes` x core quantifier: the simple summary and one restricted summary
per value of operator / product / line / canton / time_band (fast path) and weekday group.
Writes data/processed/summaries.parquet (one row per SummaryRecord, deterministic order)
and summaries_report.json: rows, dropped (NaN) rows per segment, Qc drops by quantifier,
runtime and library versions (AGENTS §4.6).
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from importlib import metadata
from pathlib import Path

import pandas as pd
import yaml

from urban_computing.evaluation.segments import (
    PARTITION_FAMILIES,
    family_codes,
    segments,
    weekday_group_masks,
)
from urban_computing.fuzzy.miner import SummaryRecord, mine, mine_categorical, qc_drop_report
from urban_computing.fuzzy.vocabulary import load_vocabulary

ROOT = Path(__file__).resolve().parents[1]
ATTRIBUTE = "arrival_delay_minutes"  # ARRIVALS.delay_min
COLUMNS = ["delay_min", "operator_abbr", "product", "line", "canton", "time_band", "weekday",
           "half"]  # fmt: skip


def mine_arrivals(
    arrivals: pd.DataFrame, config: dict, vocab_path: Path | None = None
) -> tuple[list[SummaryRecord], dict]:
    """All summary records for the arrivals table, and the report dict."""
    vocab = load_vocabulary(vocab_path or ROOT / "config" / "vocabulary.yaml")
    mining = config["mining"]
    beta, tnorm = float(mining["beta"]), str(mining["tnorm"])
    records: list[SummaryRecord] = []
    seg_report = []
    for segment, half, rows in segments(arrivals):
        values = {ATTRIBUTE: rows["delay_min"].astype("float64").to_numpy()}
        kw = {"segment": segment, "half": half, "mining": mining}
        records += mine(values, weekday_group_masks(rows), vocab, beta, tnorm=tnorm, **kw)
        for family in PARTITION_FAMILIES:
            records += mine_categorical(values, family, family_codes(rows, family), vocab, **kw)
        missing = int(rows["delay_min"].isna().sum())
        seg_report.append({"segment": segment, "half": half, "rows": int(len(rows)),
                           "dropped_missing_delay": missing})  # fmt: skip
    report = {
        "rows": int(len(arrivals)),
        "records": len(records),
        "beta": beta,
        "segments": seg_report,
        "qc_drops_by_quantifier": qc_drop_report(records, beta),
        "small_n_records": sum(r.small_n for r in records),
    }
    return records, report


def _versions() -> dict[str, str]:
    out = {"python": platform.python_version()}
    for pkg in ("numpy", "pandas", "pyarrow", "pyyaml"):
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = "not installed"
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", type=Path, default=ROOT / "config" / "study.yaml")
    ap.add_argument("--arrivals", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    processed = ROOT / config["data"]["processed_dir"]
    src = args.arrivals or processed / "arrivals.parquet"
    out = args.out or processed / "summaries.parquet"
    if not src.exists():
        print(f"{src} missing: run `make data-arrivals` (UC-013) first", file=sys.stderr)
        return 2
    t0 = time.perf_counter()
    arrivals = pd.read_parquet(src, columns=COLUMNS)
    records, report = mine_arrivals(arrivals, config)
    report["seconds"] = round(time.perf_counter() - t0, 1)
    report["versions"] = _versions()
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([r.to_dict() for r in records]).to_parquet(out, index=False)
    rep_path = out.with_name(out.stem + "_report.json")
    rep_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(records)} records, {report['seconds']} s) and {rep_path}")
    for q, d in report["qc_drops_by_quantifier"].items():
        print(f"  {q}: {d['valid']} valid (truth >= beta), {d['dropped_by_qc']} dropped by Qc")
    return 0


if __name__ == "__main__":
    sys.exit(main())
