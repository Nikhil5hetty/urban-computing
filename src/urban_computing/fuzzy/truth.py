"""Truth (validity) of linguistic summaries (UC-021). Formulas: docs/methods.md §2.

Works on membership arrays so it does not depend on the vocabulary implementation.
Pure NumPy, no I/O. Missing memberships (NaN, e.g. a cancelled train whose delay is
NaN) are dropped row-wise before aggregating; an empty or zero-weight restriction gives
NaN, which callers use as the "not computable" flag (`np.isnan`).
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from urban_computing.fuzzy.vocabulary import MembershipFn

TNorm = Literal["product", "min"]
TNORMS: tuple[str, ...] = ("product", "min")


def _memberships(mu: np.ndarray, name: str) -> np.ndarray:
    """1-D float64 view; raise ValueError if a non-NaN value is outside [0, 1]."""
    a = np.asarray(mu, dtype=np.float64).ravel()
    finite = a[~np.isnan(a)]
    if finite.size and (finite.min() < 0.0 or finite.max() > 1.0):
        raise ValueError(f"{name} must be membership degrees in [0, 1] (NaN = missing)")
    return a


def fuzzy_proportion(
    mu_S: np.ndarray, mu_R: np.ndarray | None = None, tnorm: TNorm = "product"
) -> float:
    """Fuzzy (sigma-count) proportion of rows that are S, optionally among rows that are R.

    Inputs: membership arrays in [0, 1] of equal length (NaN = missing row).
    Returns sum t(mu_R, mu_S) / sum mu_R, or mean(mu_S) if mu_R is None, as a float in
    [0, 1]. Rows with NaN in any input are dropped. NaN if no complete rows remain or
    sum mu_R == 0 (empty restriction). Raises ValueError on out-of-range memberships,
    mismatched lengths or an unknown t-norm.
    """
    if tnorm not in TNORMS:
        raise ValueError(f"tnorm must be one of {TNORMS}, got {tnorm!r}")
    s = _memberships(mu_S, "mu_S")
    if mu_R is None:
        s = s[~np.isnan(s)]
        return float(s.mean()) if s.size else float("nan")
    r = _memberships(mu_R, "mu_R")
    if r.shape != s.shape:
        raise ValueError(f"mu_R and mu_S differ in length: {r.size} != {s.size}")
    keep = ~(np.isnan(r) | np.isnan(s))
    if not keep.all():
        r, s = r[keep], s[keep]
    denom = r.sum()
    if denom <= 0.0:
        return float("nan")
    num = np.dot(r, s) if tnorm == "product" else np.minimum(r, s).sum()
    return float(num / denom)


def _apply_q(Q: MembershipFn, p: float) -> float:
    if np.isnan(p):
        return float("nan")
    return float(np.asarray(Q(np.asarray(p, dtype=np.float64))))


def truth_simple(mu_S: np.ndarray, Q: MembershipFn) -> float:
    """v("Q x are S") = mu_Q(mean(mu_S)).

    Inputs: memberships mu_S in [0, 1] (NaN rows dropped); quantifier Q on proportions.
    Returns truth in [0, 1], or NaN if there are no non-missing rows.
    """
    return _apply_q(Q, fuzzy_proportion(mu_S))


def truth_restricted(
    mu_R: np.ndarray, mu_S: np.ndarray, Q: MembershipFn, tnorm: TNorm = "product"
) -> float:
    """v("Q R x are S") = mu_Q(sum t(mu_R, mu_S) / sum mu_R); nan if sum mu_R == 0.

    Inputs: memberships mu_R (restriction) and mu_S (summarizer) in [0, 1], same length
    (rows with NaN in either are dropped); quantifier Q; t-norm "product" or "min".
    Returns truth in [0, 1], or NaN for an empty restriction.
    """
    return _apply_q(Q, fuzzy_proportion(mu_S, mu_R, tnorm))
