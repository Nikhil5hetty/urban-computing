"""Segments and restriction masks from ARRIVALS (UC-023).

Restriction families (methods §4): partition families `operator` (column operator_abbr),
`product`, `line`, `canton`, `time_band` (each arrival has at most one value), and the
overlapping `weekday_group` (weekday = Mon-Fri, monday, friday, weekend; from `weekday`).
Segments: the whole network, optionally split into the study halves (`half`).
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import pandas as pd

RESTRICTION_FAMILIES = ("operator", "product", "line", "canton", "time_band", "weekday_group")
PARTITION_FAMILIES = ("operator", "product", "line", "canton", "time_band")
FAMILY_COLUMN = {"operator": "operator_abbr"}  # family -> ARRIVALS column (default: same name)
WEEKDAY_GROUPS: dict[str, tuple[int, ...]] = {
    "weekday": (0, 1, 2, 3, 4),
    "monday": (0,),
    "friday": (4,),
    "weekend": (5, 6),
}  # "all" = no restriction
HALVES: tuple[str | None, ...] = (None, "first", "second")


def family_codes(arrivals: pd.DataFrame, family: str) -> np.ndarray:
    """Per-row value of a partition family (object array; None where missing / blank)."""
    if family not in PARTITION_FAMILIES:
        raise ValueError(f"{family!r} is not a partition family {PARTITION_FAMILIES}")
    col = arrivals[FAMILY_COLUMN.get(family, family)].astype("string").str.strip()
    col = col.mask(col == "")
    return np.array([None if pd.isna(v) else str(v) for v in col], dtype=object)


def weekday_group_masks(arrivals: pd.DataFrame) -> dict[str, np.ndarray]:
    """'weekday_group=<g>' -> 0/1 float mask from the `weekday` column (0 = Monday)."""
    wd = arrivals["weekday"].to_numpy()
    return {
        f"weekday_group={g}": np.isin(wd, days).astype(np.float64)
        for g, days in WEEKDAY_GROUPS.items()
    }


def restriction_masks(
    arrivals: pd.DataFrame, families: tuple[str, ...] = RESTRICTION_FAMILIES, min_n: int = 30
) -> dict[str, np.ndarray]:
    """Label like 'product=IC' -> 0/1 float mask over the rows of `arrivals`.

    One mask per value of each family (sorted labels); labels with fewer than `min_n` rows
    are left out (use min_n=1 to keep all; the miner flags small segments itself). Dense
    masks cost rows x labels memory: for the full data the script uses
    `fuzzy.miner.mine_categorical` with `family_codes` instead (same records).
    """
    out: dict[str, np.ndarray] = {}
    for family in families:
        if family == "weekday_group":
            masks = weekday_group_masks(arrivals)
        else:
            codes = family_codes(arrivals, family)
            values = sorted({c for c in codes if c is not None})
            masks = {f"{family}={v}": (codes == v).astype(np.float64) for v in values}
        for label in sorted(masks):
            if masks[label].sum() >= min_n:
                out[label] = masks[label]
    return out


def segments(arrivals: pd.DataFrame) -> Iterator[tuple[str, str | None, pd.DataFrame]]:
    """(segment, half, rows): the whole network, then each study half."""
    for half in HALVES:
        rows = arrivals if half is None else arrivals.loc[arrivals["half"] == half]
        yield "network", half, rows
