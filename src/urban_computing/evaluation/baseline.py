"""Unrestricted Pincay et al. (2021) methodological baseline for train arrivals."""

from math import isclose, isnan
from pathlib import Path

import pandas as pd

from urban_computing.data.arrivals import build_arrivals
from urban_computing.evaluation.registry import Context, Table, table
from urban_computing.fuzzy.truth import fuzzy_proportion
from urban_computing.fuzzy.vocabulary import load_vocabulary

_NAME = "baseline_pincay"


def _arrivals(ctx: Context) -> pd.DataFrame:
    key = "baseline_pincay_arrivals"
    if key not in ctx.cache:
        path = Path(ctx.paths["arrivals"])
        if ctx.sample and not path.exists():
            # Sample I5 has already ingested the fixture. It has no atlas export,
            # so UC-013 uses its normal fallback for unmapped stop identifiers.
            events = pd.read_parquet(Path(ctx.paths["interim_dir"]) / "ist")
            atlas = pd.DataFrame(
                columns=["sloid", "number", "isoCountryCode", "cantonAbbreviation"]
            )
            frame = build_arrivals(events, atlas, ctx.config)
        else:
            frame = pd.read_parquet(path, columns=["half", "delay_min"])
        ctx.cache[key] = frame[["half", "delay_min"]]
    return ctx.cache[key]


def _baseline(ctx: Context, name: str, half: str | None = None) -> Table:
    arrivals = _arrivals(ctx)
    delays = (
        arrivals["delay_min"]
        if half is None
        else arrivals.loc[arrivals["half"] == half, "delay_min"]
    )
    vocabulary = load_vocabulary(Path(ctx.paths["vocabulary"]))
    beta = float(ctx.config["mining"]["beta"])  # Pincay et al., §3.2, p. 172: 0.6
    summarizers = vocabulary.summarizers["arrival_delay_minutes"]
    # Eq. (2), p. 170 (methods §2). Reuse the sigma-count across the three quantifiers.
    proportions = {
        word: fuzzy_proportion(membership(delays.to_numpy()))
        for word, membership in summarizers.items()
    }
    rows = []
    for quantifier, membership in vocabulary.quantifiers["pincay2021"].items():
        for summarizer, proportion in proportions.items():
            truth = float(membership(proportion))
            # Preserve equality at beta when a trapezoid ramp rounds just below it.
            rows.append(
                {
                    "quantifier": quantifier,
                    "summarizer": summarizer,
                    "truth": None if isnan(truth) else truth,
                    "valid": truth >= beta or isclose(truth, beta, rel_tol=0, abs_tol=1e-15),
                }
            )
    return Table(name, rows)


@table(_NAME)
def baseline_pincay(ctx: Context) -> Table:
    """Return 12 network-wide truth scores in [0, 1] from arrival delays in minutes."""
    return _baseline(ctx, _NAME)


@table(f"{_NAME}_first")
def baseline_pincay_first(ctx: Context) -> Table:
    """Return the 12 truth scores in [0, 1] for first-half arrival delays in minutes."""
    return _baseline(ctx, f"{_NAME}_first", "first")


@table(f"{_NAME}_second")
def baseline_pincay_second(ctx: Context) -> Table:
    """Return the 12 truth scores in [0, 1] for second-half arrival delays in minutes."""
    return _baseline(ctx, f"{_NAME}_second", "second")
