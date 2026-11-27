"""SRQ1 "Is the answer about my trip?": coverage, regional masking and ranking change (UC-050).

All three hypotheses use the summaries mined from ARRIVALS exactly as the UC-023 miner does
(network segment, whole period and each study half; restriction families operator, product,
line, canton, time band and weekday group; Q_c with `mining.qc_tnorm`).

- H1a `share_valid_but_low_coverage`: among restricted summaries of the two halves (pooled;
  the whole-period copies are left out so no summary is counted twice) with truth v ≥ β,
  the share with coverage C < `mining.coverage_threshold`. Wilson 95 % CI. Breakdowns by
  restriction family and by R's share of the segment |R|/n (i_C ≤ |R|/n, so R below r1 of
  the segment always has C = 0) are reported next to it (PM review of #55).
- H1b `n_stable_masking_cases`: a case is a local restriction R (operator, canton = region,
  or line) and a summarizer S whose best valid local quantifier differs from the best valid
  network-wide quantifier for S, in both halves. "Best" = highest truth among quantifiers
  with v ≥ β; ties are broken by the quantifier order few < about_half < most. Each case
  carries a citizen-readable sentence pair (network vs local, first half).
- H1c `kendall_tau_top20`: the 20 restricted summaries of the whole period with the highest
  validity v (ties broken by larger n, then by sentence, so that Q_c plays no part in the
  selection), Kendall τ-b between their v and Q_c values with a seeded permutation p-value.
  Reported again for restrictions with |R| ≥ r1 of the segment (PM review of #55).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from urban_computing.evaluation.invariants import _i4_tables
from urban_computing.evaluation.registry import Context, Result, Table, experiment, table
from urban_computing.evaluation.segments import (
    PARTITION_FAMILIES,
    RESTRICTION_FAMILIES,
    family_codes,
    segments,
    weekday_group_masks,
)
from urban_computing.evaluation.stats import kendall_tau_perm, wilson_ci
from urban_computing.fuzzy.miner import SummaryRecord, mine, mine_categorical
from urban_computing.fuzzy.vocabulary import load_vocabulary

ATTRIBUTE = "arrival_delay_minutes"
MASKING_FAMILIES = ("operator", "canton", "line")  # "operator, region or line" (H1b)
QUANTIFIER_ORDER = ("few", "about_half", "most")
TOP_K = 20
HALVES = ("first", "second")


@dataclass
class _Mined:
    records: list[SummaryRecord]
    n_complete: dict[str | None, int]  # half -> complete (non-missing) rows of the segment


def _family(record: SummaryRecord) -> str:
    return (record.restriction or "").split("=", 1)[0]


def _mine(ctx: Context) -> _Mined:
    if "srq1_mined" in ctx.cache:
        return ctx.cache["srq1_mined"]
    arrivals, _, _ = _i4_tables(ctx)
    vocab = load_vocabulary(Path(ctx.paths.get("vocabulary", "config/vocabulary.yaml")))
    mining = ctx.config["mining"]
    beta, tnorm = float(mining["beta"]), str(mining["tnorm"])
    records: list[SummaryRecord] = []
    n_complete: dict[str | None, int] = {}
    for segment, half, rows in segments(arrivals):
        values = {ATTRIBUTE: rows["delay_min"].astype("float64").to_numpy()}
        kw = {"segment": segment, "half": half, "mining": mining}
        records += mine(values, weekday_group_masks(rows), vocab, beta, tnorm=tnorm, **kw)
        for family in PARTITION_FAMILIES:
            records += mine_categorical(values, family, family_codes(rows, family), vocab, **kw)
        n_complete[half] = int(rows["delay_min"].notna().sum())
    ctx.cache["srq1_mined"] = _Mined(records, n_complete)
    return ctx.cache["srq1_mined"]


def _settings(ctx: Context) -> tuple[float, float, float]:
    mining = ctx.config["mining"]
    return (
        float(mining["beta"]),
        float(mining["coverage_threshold"]),
        float(mining.get("coverage_r1", 0.02)),
    )


def _share(record: SummaryRecord, mined: _Mined) -> float:
    total = mined.n_complete.get(record.half, 0)
    return record.n / total if total else float("nan")


def _valid_restricted(records, beta: float, halves) -> list[SummaryRecord]:
    return [
        r
        for r in records
        if r.protoform == "restricted"
        and r.half in halves
        and r.truth is not None
        and np.isfinite(r.truth)
        and r.truth >= beta
    ]


def _proportion(low: list[SummaryRecord], valid: list[SummaryRecord]) -> dict:
    n, k = len(valid), len(low)
    point, ci_low, ci_high = wilson_ci(k, n) if n else (None, None, None)
    return {"n_valid": n, "n_low_coverage": k, "point": point, "ci_low": ci_low, "ci_high": ci_high}


@experiment("H1a")
def h1a(ctx: Context) -> Result:
    """Share of valid restricted summaries (v ≥ β, halves pooled) with C below the threshold.

    Returns the proportion with a Wilson 95 % CI, plus breakdowns by restriction family and
    by |R|/n below or at least r1 (proportions, unitless).
    """
    mined = _mine(ctx)
    beta, c_min, r1 = _settings(ctx)
    valid = _valid_restricted(mined.records, beta, HALVES)
    low = [r for r in valid if r.coverage is None or r.coverage < c_min]
    overall = _proportion(low, valid)

    by_family = {}
    for family in RESTRICTION_FAMILIES:
        v = [r for r in valid if _family(r) == family]
        by_family[family] = _proportion([r for r in low if _family(r) == family], v)
    is_small = {id(r): _share(r, mined) < r1 for r in valid}
    small = [r for r in valid if is_small[id(r)]]
    large = [r for r in valid if not is_small[id(r)]]
    by_size = {
        "below_r1": _proportion([r for r in low if is_small[id(r)]], small),
        "at_least_r1": _proportion([r for r in low if not is_small[id(r)]], large),
    }
    details = {
        "beta": beta,
        "coverage_threshold": c_min,
        "r1": r1,
        "restriction_families": list(RESTRICTION_FAMILIES),
        "n_valid": overall["n_valid"],
        "n_low_coverage": overall["n_low_coverage"],
        "n_low_coverage_from_small_r": sum(1 for r in low if is_small[id(r)]),
        "by_family": by_family,
        "by_r_share": by_size,
        "n_small_n_valid": sum(r.small_n for r in valid),
    }
    return Result(
        point=overall["point"],
        ci_low=overall["ci_low"],
        ci_high=overall["ci_high"],
        details=details,
    )


def _best(records: list[SummaryRecord], beta: float) -> SummaryRecord | None:
    valid = [r for r in records if r.truth is not None and np.isfinite(r.truth) and r.truth >= beta]
    if not valid:
        return None
    rank = {q: i for i, q in enumerate(QUANTIFIER_ORDER)}
    return max(valid, key=lambda r: (r.truth, rank.get(r.quantifier, -1)))


def _masking_cases(ctx: Context) -> list[dict]:
    if "srq1_masking" in ctx.cache:
        return ctx.cache["srq1_masking"]
    mined = _mine(ctx)
    beta = _settings(ctx)[0]
    network: dict[tuple, list] = defaultdict(list)
    local: dict[tuple, list] = defaultdict(list)
    for r in mined.records:
        if r.half not in HALVES:
            continue
        if r.protoform == "simple":
            network[(r.half, r.summarizer)].append(r)
        elif _family(r) in MASKING_FAMILIES:
            local[(r.half, r.restriction, r.summarizer)].append(r)

    per_half: dict[tuple, dict] = {}
    for (half, restriction, summarizer), recs in local.items():
        loc, net = _best(recs, beta), _best(network[(half, summarizer)], beta)
        if loc is not None and net is not None and loc.quantifier != net.quantifier:
            per_half[(half, restriction, summarizer)] = {"local": loc, "network": net}

    cases = []
    for (half, restriction, summarizer), pair in sorted(per_half.items(), key=lambda x: x[0][1:]):
        if half != HALVES[0] or (HALVES[1], restriction, summarizer) not in per_half:
            continue
        second = per_half[(HALVES[1], restriction, summarizer)]
        cases.append(
            {
                "restriction": restriction,
                "family": restriction.split("=", 1)[0],
                "summarizer": summarizer,
                "network_quantifier_first": pair["network"].quantifier,
                "local_quantifier_first": pair["local"].quantifier,
                "network_quantifier_second": second["network"].quantifier,
                "local_quantifier_second": second["local"].quantifier,
                "network_sentence": pair["network"].sentence,
                "network_truth": round(pair["network"].truth, 4),
                "local_sentence": pair["local"].sentence,
                "local_truth": round(pair["local"].truth, 4),
                "local_n": pair["local"].n,
            }
        )
    ctx.cache["srq1_masking"] = cases
    return cases


@experiment("H1b")
def h1b(ctx: Context) -> Result:
    """Count (value) of stable masking cases with up to ten listed sentence pairs."""
    cases = _masking_cases(ctx)
    families = defaultdict(int)
    for case in cases:
        families[case["family"]] += 1
    details = {
        "masking_families": list(MASKING_FAMILIES),
        "by_family": dict(families),
        "examples": cases[:10],
    }
    return Result(value=float(len(cases)), details=details)


def _top(records: list[SummaryRecord], k: int = TOP_K) -> list[SummaryRecord]:
    usable = [r for r in records if r.quality is not None and np.isfinite(r.quality)]
    return sorted(usable, key=lambda r: (-r.truth, -r.n, r.sentence))[:k]


def _tau(records: list[SummaryRecord], ctx: Context) -> dict:
    top = _top(records)
    out = {"n": len(top)}
    if len(top) < 2:
        return {**out, "tau": None, "p": None}
    truth = [r.truth for r in top]
    quality = [r.quality for r in top]
    if len(set(truth)) < 2 or len(set(quality)) < 2:
        # τ-b is undefined when one ranking is constant; report it rather than guess.
        return {**out, "tau": None, "p": None, "constant_ranking": True}
    n_perm = int(ctx.config["evaluation"].get("bootstrap_resamples", 2000))
    tau, p = kendall_tau_perm(truth, quality, n_perm=n_perm, seed=ctx.seed)
    return {**out, "tau": tau, "p": p}


@experiment("H1c")
def h1c(ctx: Context) -> Result:
    """Kendall τ-b between v and Q_c over the top-20 restricted summaries by v (whole period).

    Also reported for restrictions with |R| ≥ r1 of the segment (`details.large_r`).
    """
    mined = _mine(ctx)
    r1 = _settings(ctx)[2]
    restricted = [
        r
        for r in mined.records
        if r.protoform == "restricted"
        and r.half is None
        and r.truth is not None
        and np.isfinite(r.truth)
    ]
    main = _tau(restricted, ctx)
    large = _tau([r for r in restricted if _share(r, mined) >= r1], ctx)
    top = _top(restricted)
    details = {
        "n_top": main["n"],
        "large_r": large,
        "top20": [
            {"sentence": r.sentence, "truth": r.truth, "quality": r.quality, "n": r.n} for r in top
        ],
    }
    if main.get("constant_ranking"):
        details["reason"] = "constant_ranking"
    return Result(point=main["tau"], p=main["p"], details=details)


@table("srq1_masking_cases")
def masking_table(ctx: Context) -> Table:
    """All stable masking cases (H1b) with both halves' quantifiers and the sentence pair."""
    return Table("srq1_masking_cases", _masking_cases(ctx))


@table("srq1_coverage_breakdown")
def coverage_table(ctx: Context) -> Table:
    """H1a by restriction family and by |R|/n (below / at least r1), one row per group."""
    result = h1a(ctx)
    rows = [
        {
            "group": "all",
            **{k: result.details[k] for k in ("n_valid", "n_low_coverage")},
            "point": result.point,
            "ci_low": result.ci_low,
            "ci_high": result.ci_high,
        }
    ]
    for family, stats in result.details["by_family"].items():
        rows.append({"group": f"family={family}", **stats})
    for size, stats in result.details["by_r_share"].items():
        rows.append({"group": f"r_share={size}", **stats})
    if "results_dir" in ctx.paths:
        _coverage_figure(rows, Path(ctx.paths["results_dir"]) / "figures" / "srq1_coverage.png")
    return Table("srq1_coverage_breakdown", rows)


def _coverage_figure(rows: list[dict], path: Path) -> None:
    """Bar chart: share of valid restricted summaries with low coverage, per group."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    shown = [r for r in rows if r["group"] != "all" and r.get("n_valid")]
    if not shown:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    labels = [r["group"].split("=", 1)[1].replace("_", " ") for r in shown]
    ax.bar(labels, [r["point"] for r in shown], color="#4a6fa5")
    ax.set_ylim(0, 1)
    ax.set_ylabel("share with C below threshold")
    ax.set_title("Valid restricted summaries with low coverage (H1a)")
    ax.tick_params(axis="x", labelrotation=30)
    fig.tight_layout()
    fig.savefig(path, dpi=150, metadata={"Software": None})
    plt.close(fig)
