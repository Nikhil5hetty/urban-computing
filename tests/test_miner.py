"""UC-023: summary miner, restriction masks and the mining script (synthetic data only)."""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from tests import factories
from urban_computing.evaluation.segments import (
    PARTITION_FAMILIES,
    family_codes,
    restriction_masks,
    weekday_group_masks,
)
from urban_computing.fuzzy.miner import (
    SummaryRecord,
    mine,
    mine_categorical,
    qc_drop_report,
    render_sentence,
)
from urban_computing.fuzzy.quality import coverage, quality_qc
from urban_computing.fuzzy.truth import truth_restricted, truth_simple
from urban_computing.fuzzy.vocabulary import load_vocabulary

ROOT = Path(__file__).resolve().parents[1]
VOCAB = load_vocabulary(ROOT / "config" / "vocabulary.yaml")
CONFIG = yaml.safe_load((ROOT / "config" / "study.yaml").read_text())
MINING = CONFIG["mining"]
D = "arrival_delay_minutes"
SEED = CONFIG["study"]["seed"]


def synthetic_arrivals(n: int = 3000, seed: int = SEED) -> pd.DataFrame:
    """Random ARRIVALS-like frame (only the columns the miner uses)."""
    rng = np.random.default_rng(seed)
    delay = rng.gamma(1.2, 2.0, n) - 0.5
    delay[rng.random(n) < 0.03] = np.nan  # cancelled / unmeasured
    return pd.DataFrame(
        {
            "delay_min": delay,
            "operator_abbr": rng.choice(["SBB", "BLS", "SOB"], n, p=[0.7, 0.2, 0.1]),
            "product": rng.choice(["IC", "IR", "RE", "S"], n),
            "line": rng.choice(["IC1", "IC5", "IR16", "S3", "S9", "RE7"], n),
            "canton": rng.choice(["ZH", "BE", "SO", ""], n, p=[0.4, 0.3, 0.25, 0.05]),
            "time_band": rng.choice(["morning_peak", "midday", "evening_peak", "night"], n),
            "weekday": rng.integers(0, 7, n),
            "half": rng.choice(["first", "second"], n),
        }
    )


def _key(r: SummaryRecord) -> tuple:
    return (r.summarizer, r.quantifier, r.restriction)


# --------------------------------------------------------------------- valid set at beta


def test_known_proportions_give_expected_valid_set():
    # IC: 80 % fully late (6 min), 20 % on time (0 min); IR: all on time
    delays = np.array([6.0] * 80 + [0.0] * 20 + [0.0] * 100)
    product = np.array(["IC"] * 100 + ["IR"] * 100, dtype=object)
    recs = mine_categorical({D: delays}, "product", product, VOCAB, mining=MINING)
    valid = {(r.restriction, r.summarizer.split(":")[1], r.quantifier): round(r.truth, 4)
             for r in recs if r.truth >= MINING["beta"]}  # fmt: skip
    assert valid == {
        ("product=IC", "late", "most"): round((0.8 - 0.5) / 0.35, 4),  # 0.8571
        ("product=IC", "on_time", "few"): 0.6,  # mu_few(0.2) = (0.35 - 0.2) / 0.25, == beta
        ("product=IR", "on_time", "most"): 1.0,
        ("product=IR", "slightly_late", "few"): 1.0,
        ("product=IR", "late", "few"): 1.0,
        ("product=IR", "very_late", "few"): 1.0,
        ("product=IC", "slightly_late", "few"): 1.0,
        ("product=IC", "very_late", "few"): 1.0,
    }


# --------------------------------------------------------------------- truth recomputes


def test_spot_check_100_records_recompute_from_stored_masks():
    df = synthetic_arrivals()
    masks = restriction_masks(df, min_n=1)
    values = {D: df["delay_min"].to_numpy()}
    recs = mine(values, masks, VOCAB, MINING["beta"], mining=MINING)
    restricted = [r for r in recs if r.protoform == "restricted"]
    rng = np.random.default_rng(SEED)
    for i in rng.choice(len(restricted), 100, replace=False):
        r = restricted[int(i)]
        word = VOCAB.summarizers[D][r.summarizer.split(":")[1]]
        q = VOCAB.quantifiers["core"][r.quantifier]
        mu_s = word(values[D])
        assert r.truth == pytest.approx(truth_restricted(masks[r.restriction], mu_s, q), abs=1e-12)
        assert r.coverage == pytest.approx(coverage(masks[r.restriction], mu_s, MINING))
        assert r.quality == pytest.approx(quality_qc(r.truth, r.coverage))


def test_fast_path_equals_generic_mine_with_dense_masks():
    df = synthetic_arrivals()
    values = {D: df["delay_min"].to_numpy()}
    for family in PARTITION_FAMILIES:
        codes = family_codes(df, family)
        fast = mine_categorical(values, family, codes, VOCAB, mining=MINING)
        dense = restriction_masks(df, (family,), min_n=1)
        slow = mine(values, dense, VOCAB, mining=MINING, include_simple=False)
        assert [_key(r) for r in fast] == [_key(r) for r in slow]
        for a, b in zip(fast, slow, strict=True):
            assert (a.n, a.n_dropped, a.sentence, a.small_n) == (b.n, b.n_dropped, b.sentence,
                                                                 b.small_n)  # fmt: skip
            assert a.truth == pytest.approx(b.truth, abs=1e-12)
            assert a.coverage == pytest.approx(b.coverage, abs=1e-12)
            assert a.quality == pytest.approx(b.quality, abs=1e-12)


def test_simple_summaries_and_record_shape():
    df = synthetic_arrivals(500)
    recs = mine({D: df["delay_min"].to_numpy()}, {}, VOCAB, mining=MINING)
    assert len(recs) == 4 * 3  # 4 words x 3 core quantifiers
    mu = VOCAB.summarizers[D]["on_time"](df["delay_min"].to_numpy())
    r = next(r for r in recs if r.summarizer == f"{D}:on_time" and r.quantifier == "most")
    assert r.truth == pytest.approx(truth_simple(mu, VOCAB.quantifiers["core"]["most"]))
    assert (r.protoform, r.restriction, r.segment, r.half) == ("simple", None, "network", None)
    assert set(SummaryRecord.__dataclass_fields__) >= {"truth", "coverage", "quality", "n",
                                                       "sentence", "n_dropped"}  # fmt: skip


# --------------------------------------------------------------------- coverage / Qc (#54)


def test_unrestricted_qc_equals_truth_and_qc_uses_product_even_for_min_truth():
    df = synthetic_arrivals(800)
    values = {D: df["delay_min"].to_numpy()}
    recs = mine(values, weekday_group_masks(df), VOCAB, tnorm="min", mining=MINING)
    for r in recs:
        if r.protoform == "simple":
            assert r.coverage == 1.0 and r.quality == pytest.approx(r.truth)
        elif r.quality is not None:
            assert r.quality <= r.truth + 1e-12  # product Qc, never min (D-027)


def test_restricted_few_gets_low_coverage_and_is_reported():
    # a tiny restriction where "few are late" is fully true but covers < r1 of the records
    delays = np.zeros(2000)
    codes = np.array(["tiny"] * 20 + ["big"] * 1980, dtype=object)
    recs = mine_categorical({D: delays}, "line", codes, VOCAB, mining=MINING)
    few_late = next(r for r in recs if r.restriction == "line=tiny" and r.quantifier == "few"
                    and r.summarizer.endswith(":late"))  # fmt: skip
    assert few_late.truth == 1.0 and few_late.coverage == 0.0 and few_late.quality == 0.0
    rep = qc_drop_report(recs, MINING["beta"])
    assert rep["few"]["valid"] >= 1 and rep["few"]["dropped_by_qc"] >= 1
    assert set(rep) <= {"few", "about_half", "most"}


# --------------------------------------------------------------------- n, dropped, small_n


def test_n_counts_complete_rows_and_reports_dropped():
    delays = np.array([1.0, 2.0, np.nan, np.nan, 5.0] + [0.0] * 40)
    codes = np.array(["a"] * 5 + ["b"] * 40, dtype=object)
    recs = mine_categorical({D: delays}, "line", codes, VOCAB, mining=MINING)
    a = next(r for r in recs if r.restriction == "line=a")
    b = next(r for r in recs if r.restriction == "line=b")
    assert (a.n, a.n_dropped, a.small_n) == (3, 2, True)  # kept but flagged (< 30)
    assert (b.n, b.n_dropped, b.small_n) == (40, 0, False)
    simple = mine({D: delays}, {}, VOCAB, mining=MINING)[0]
    assert (simple.n, simple.n_dropped) == (43, 2)


def test_empty_restriction_has_nan_truth_and_no_quality():
    delays = np.array([np.nan, np.nan, 1.0])
    codes = np.array(["x", "x", "y"], dtype=object)
    x = next(r for r in mine_categorical({D: delays}, "line", codes, VOCAB) if r.restriction ==
             "line=x")  # fmt: skip
    assert math.isnan(x.truth) and x.coverage is None and x.quality is None and x.n == 0


# --------------------------------------------------------------------- rendering


@pytest.mark.parametrize(
    "q,s,r,seg,expected",
    [
        ("about_half", f"{D}:slightly_late", "product=IC&time_band=morning_peak", "network",
         "About half of the IC arrivals in the morning peak are slightly late."),
        ("most", f"{D}:on_time", None, "network", "Most of the arrivals are on time."),
        ("few", f"{D}:very_late", "line=IC1&weekday_group=monday", "network",
         "Few of the IC1 arrivals on Mondays are very late."),
        ("most", f"{D}:late", "canton=BE&time_band=night", "network",
         "Most of the arrivals in canton BE at night are late."),
        ("few", "connection_slack_minutes:missed", "weekday_group=weekend", "hub=Olten",
         "Few of the connections at Olten at weekends are missed."),
        ("about_half", f"{D}:on_time", "operator=SBB&product=IR", "network",
         "About half of the SBB IR arrivals are on time."),
    ],
)  # fmt: skip
def test_sentence_snapshots(q, s, r, seg, expected):
    assert render_sentence(q, s, r, seg) == expected
    assert render_sentence(q, s, r, seg) == render_sentence(q, s, r, seg)  # deterministic


# --------------------------------------------------------------------- segments


def test_restriction_masks_labels_and_min_n():
    df = synthetic_arrivals(1000)
    masks = restriction_masks(df, min_n=1)
    assert "product=IC" in masks and "operator=SBB" in masks and "weekday_group=monday" in masks
    assert not any(k.startswith("canton=") and k.endswith("=") for k in masks)  # blank canton
    assert all(set(np.unique(m)) <= {0.0, 1.0} and m.size == len(df) for m in masks.values())
    assert (masks["weekday_group=weekday"] >= masks["weekday_group=monday"]).all()
    few = restriction_masks(df, ("operator",), min_n=150)
    assert set(few) == {f"operator={o}" for o, c in df["operator_abbr"].value_counts().items()
                        if c >= 150}  # fmt: skip
    codes = family_codes(df, "canton")
    assert None in set(codes) and "" not in set(codes)
    with pytest.raises(ValueError):
        family_codes(df, "weekday_group")


# --------------------------------------------------------------------- script


def _load_script():
    path = ROOT / "scripts" / "mine_summaries.py"
    spec = importlib.util.spec_from_file_location("mine_summaries", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mine_summaries"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_script_writes_summaries_and_report(tmp_path):
    import json

    ms = _load_script()
    df = synthetic_arrivals(2000)
    src = tmp_path / "arrivals.parquet"
    df.to_parquet(src)
    out = tmp_path / "summaries.parquet"
    assert ms.main(["--arrivals", str(src), "--out", str(out)]) == 0
    s = pd.read_parquet(out)
    assert set(s.columns) == set(SummaryRecord.__dataclass_fields__)
    assert set(s["half"].dropna()) == {"first", "second"} and s["half"].isna().any()
    rep = json.loads((tmp_path / "summaries_report.json").read_text())
    assert rep["rows"] == 2000 and rep["records"] == len(s)
    assert rep["segments"][0]["dropped_missing_delay"] == int(df["delay_min"].isna().sum())
    assert "few" in rep["qc_drops_by_quantifier"] and "numpy" in rep["versions"]
    out2 = tmp_path / "again.parquet"
    ms.main(["--arrivals", str(src), "--out", str(out2)])
    pd.testing.assert_frame_equal(s, pd.read_parquet(out2))  # deterministic
    assert ms.main(["--arrivals", str(tmp_path / "nope.parquet"), "--out", str(out)]) == 2


def test_script_on_factory_arrivals_schema():
    ms = _load_script()
    arrivals = factories.arrivals([0.0, 1.0, 4.0, None, 12.0] * 10)
    records, report = ms.mine_arrivals(arrivals, CONFIG)
    assert records and report["segments"][0]["dropped_missing_delay"] == 10
    assert any(r.restriction == "line=IC1" for r in records)


def test_make_mine_target():
    mk = (ROOT / "Makefile").read_text()
    assert "scripts/mine_summaries.py" in mk[mk.index("\nmine:") :].split("\n\n")[0]
