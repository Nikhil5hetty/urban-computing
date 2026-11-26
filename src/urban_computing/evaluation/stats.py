"""Statistics wrappers (UC-053). Stub. Thin wrappers over scipy/statsmodels."""

from __future__ import annotations

import numpy as np


def wilson_ci(successes: int, n: int, alpha: float = 0.05) -> tuple[float, float, float]:
    """(point, ci_low, ci_high) Wilson score interval."""
    raise NotImplementedError("UC-053")


def mcnemar(b: int, c: int) -> float:
    """p-value; exact binomial if b + c < 25 else chi-square with continuity correction."""
    raise NotImplementedError("UC-053")


def wilcoxon_paired(x: np.ndarray, y: np.ndarray) -> float:
    """Two-sided Wilcoxon signed-rank p-value."""
    raise NotImplementedError("UC-053")


def kendall_tau_perm(a: list, b: list, n_perm: int, seed: int) -> tuple[float, float]:
    """(tau, permutation p-value)."""
    raise NotImplementedError("UC-053")


def fisher_exact(table: list[list[int]]) -> float:
    """Two-sided Fisher exact p-value for a 2x2 table."""
    raise NotImplementedError("UC-053")


def bootstrap_ci(
    values: np.ndarray, stat, n_resamples: int, seed: int, alpha: float = 0.05
) -> tuple[float, float, float]:
    """(point, ci_low, ci_high) percentile bootstrap."""
    raise NotImplementedError("UC-053")
