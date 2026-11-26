"""Segments and restriction masks from ARRIVALS (UC-023). Stub."""

from __future__ import annotations

import numpy as np
import pandas as pd

RESTRICTION_FAMILIES = ("operator", "product", "line", "canton", "time_band", "weekday_group")


def restriction_masks(
    arrivals: pd.DataFrame, families: tuple[str, ...] = RESTRICTION_FAMILIES, min_n: int = 30
) -> dict[str, np.ndarray]:
    """Label like 'product=IC' -> 0/1 float mask over the rows of `arrivals`."""
    raise NotImplementedError("UC-023")
