"""Hudec quality measures (UC-022). Formulas: docs/methods.md §3 (verified in UC-002, D-027).

Pure NumPy, no I/O. Sources: hudec2018 (J. Official Statistics 34(4)) and hudec2022
(Informatica 33(2)); page and equation numbers in the docstrings are the journals'.
Missing memberships (NaN) are dropped row-wise, as in the truth engine (methods §2).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np

DEFAULT_COVERAGE: dict[str, float] = {"coverage_r1": 0.02, "coverage_r2": 0.15}
"""hudec2018 p. 1002 "suggested values"; mirrors config `mining.coverage_r1/r2` (D-027)."""

ORDINAL_SUM_SPLIT = 0.5  # a in hudec2022 Eq. (13)
NONIDEMPOTENT_TNORMS: tuple[str, ...] = ("product",)


def _memberships(mu: np.ndarray, name: str) -> np.ndarray:
    a = np.asarray(mu, dtype=np.float64).ravel()
    finite = a[~np.isnan(a)]
    if finite.size and (finite.min() < 0.0 or finite.max() > 1.0):
        raise ValueError(f"{name} must be membership degrees in [0, 1] (NaN = missing)")
    return a


def _coverage_params(params: Mapping[str, Any] | None) -> tuple[float, float]:
    """(r1, r2) from `mining` params, a whole config ({"mining": ...}) or the defaults."""
    p: Mapping[str, Any] = params or {}
    if "mining" in p and isinstance(p["mining"], Mapping):
        p = p["mining"]
    r1 = float(p.get("coverage_r1", DEFAULT_COVERAGE["coverage_r1"]))
    r2 = float(p.get("coverage_r2", DEFAULT_COVERAGE["coverage_r2"]))
    if not 0.0 <= r1 < r2 <= 1.0:
        raise ValueError(f"need 0 <= r1 < r2 <= 1, got r1={r1}, r2={r2}")
    return r1, r2


def included_ratio(mu_R: np.ndarray | None, mu_S: np.ndarray) -> float:
    """Ratio of included records i_C = (1/n) sum m_i (hudec2018 Eq. (A.3), p. 1002 =
    hudec2022 Eq. (18), p. 332).

    m_i = 1 iff mu_S(x_i) > 0 and mu_R(x_i) > 0 (crisp support; any degree above 0 counts),
    n = all (non-missing) records, not only those in R. mu_R None = no restriction (1).
    Returns a float in [0, 1]; NaN if there are no records.
    """
    s = _memberships(mu_S, "mu_S")
    r = np.ones_like(s) if mu_R is None else _memberships(mu_R, "mu_R")
    if r.shape != s.shape:
        raise ValueError(f"mu_R and mu_S differ in length: {r.size} != {s.size}")
    keep = ~(np.isnan(r) | np.isnan(s))
    if not keep.any():
        return float("nan")
    return float(np.mean((s[keep] > 0.0) & (r[keep] > 0.0)))


def coverage_from_ratio(i_c: float, r1: float, r2: float) -> float:
    """Degree of sufficient coverage C = f(i_C) (hudec2018 Eq. (A.4), p. 1002 = hudec2022
    Eq. (19), p. 332; attributed to Wu, Mendel & Joo 2010).

    0 if i_C <= r1; 2 (i_C - r1)^2 / (r2 - r1)^2 if r1 < i_C < (r1 + r2)/2;
    1 - 2 (r2 - i_C)^2 / (r2 - r1)^2 if (r1 + r2)/2 <= i_C < r2; 1 if i_C >= r2.
    """
    if math.isnan(i_c):
        return float("nan")
    if i_c <= r1:
        return 0.0
    if i_c >= r2:
        return 1.0
    width2 = (r2 - r1) ** 2
    if i_c < (r1 + r2) / 2:
        return 2.0 * (i_c - r1) ** 2 / width2
    return 1.0 - 2.0 * (r2 - i_c) ** 2 / width2


def coverage(mu_R: np.ndarray | None, mu_S: np.ndarray, params: dict | None = None) -> float:
    """Degree of sufficient coverage C in [0, 1] of "Q R x are S" (hudec2018 Eqs. (A.3)-(A.4),
    p. 1002 = hudec2022 Eqs. (18)-(19), p. 332).

    Inputs: memberships mu_R (None = no restriction) and mu_S in [0, 1], same length;
    `params` = config `mining` (or a whole config) with `coverage_r1`, `coverage_r2`
    (defaults: D-027 values 0.02 / 0.15). Returns C = f(i_C) (see `included_ratio`,
    `coverage_from_ratio`); NaN if there are no records. Raises ValueError on bad input.
    """
    r1, r2 = _coverage_params(params)
    return coverage_from_ratio(included_ratio(mu_R, mu_S), r1, r2)


def quality_qc(truth: float, cov: float, tnorm: str = "product", c_min: float = 0.5) -> float:
    """Qc = t(truth, C) if C >= c_min else 0 (hudec2018 Eq. (9), p. 987).

    Inputs: validity v and coverage C in [0, 1]; t must be a nonidempotent t-norm (only
    "product"; the paper's example), also when the truth ablation uses min (D-027,
    `mining.qc_tnorm`); c_min = `mining.coverage_threshold` (0.5). With the product,
    Qc <= v. NaN in either input gives NaN. Raises ValueError for another t-norm or
    inputs outside [0, 1].
    """
    if tnorm not in NONIDEMPOTENT_TNORMS:
        raise ValueError(
            f"Qc needs a nonidempotent t-norm (hudec2018 Eq. (9)); got {tnorm!r}, use 'product'"
        )
    if math.isnan(truth) or math.isnan(cov):
        return float("nan")
    if not (0.0 <= truth <= 1.0 and 0.0 <= cov <= 1.0):
        raise ValueError(f"truth and coverage must be in [0, 1], got {truth}, {cov}")
    return float(truth * cov) if cov >= c_min else 0.0


def ordinal_sum(x: float, y: float, a: float = ORDINAL_SUM_SPLIT) -> float:
    """Ordinal sum A(x, y) = A1(a ^ x, a ^ y) + A2(a v x, a v y) - a (hudec2022 Eq. (13), p. 330).

    A1(x, y) = 2xy on [0, a]^2 (rescaled product, Eq. (14)); A2(x, y) = -1 + 2x + 2y - 2xy
    on [a, 1]^2 (rescaled probabilistic sum, Eq. (15)); in the mixed regions this is
    x + y - 1/2 (Eq. (16), p. 331). Formulas for a = 0.5, as in the paper.
    """
    lo_x, lo_y, hi_x, hi_y = min(a, x), min(a, y), max(a, x), max(a, y)
    a1 = 2.0 * lo_x * lo_y
    a2 = -1.0 + 2.0 * hi_x + 2.0 * hi_y - 2.0 * hi_x * hi_y
    return float(a1 + a2 - a)


def regional_quality(
    per_region_truth: dict[str, float], region_sizes: dict[str, float]
) -> dict[str, float]:
    """Regional quality of one summary per region (hudec2022 §3.1, pp. 327-331).

    Inputs: truth v_i of the summary in each region and the region's number of records N_i
    (same keys). p_i = N_i / max_j N_j (Eq. (8), p. 327); A_i = ordinal sum A(v_i, p_i)
    (Eqs. (13)-(16)); A_i = 0 when v_i = 0 (pp. 329, 331: quality is only activated for
    truth > 0); NaN truth gives NaN. Returns {region: A_i in [0, 1]}. Raises ValueError if
    the keys differ, a size is negative or all sizes are 0.
    """
    if set(per_region_truth) != set(region_sizes):
        raise ValueError("per_region_truth and region_sizes must have the same regions")
    sizes = {k: float(v) for k, v in region_sizes.items()}
    if any(v < 0 for v in sizes.values()):
        raise ValueError("region sizes must be >= 0")
    n_max = max(sizes.values(), default=0.0)
    if n_max <= 0:
        raise ValueError("at least one region needs records")
    out: dict[str, float] = {}
    for region, v in per_region_truth.items():
        v = float(v)
        if math.isnan(v):
            out[region] = float("nan")
        elif v == 0.0:
            out[region] = 0.0
        else:
            out[region] = ordinal_sum(v, sizes[region] / n_max)
    return out
