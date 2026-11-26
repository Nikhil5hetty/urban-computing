"""Statistical tests and confidence intervals for the registered experiments."""

from collections.abc import Callable

import numpy as np
from scipy import stats
from statsmodels.stats import contingency_tables
from statsmodels.stats.proportion import proportion_confint


def wilson_ci(successes: int, n: int, alpha: float = 0.05) -> tuple[float, float, float]:
    """Return the observed proportion and Wilson bounds at confidence 1 − alpha."""
    if not 0 <= successes <= n or not 0 < alpha < 1:
        raise ValueError("Expected 0 <= successes <= n and 0 < alpha < 1")
    if n == 0:
        return (float("nan"),) * 3
    low, high = proportion_confint(successes, n, alpha=alpha, method="wilson")
    return successes / n, float(low), float(high)


def mcnemar(b: int, c: int) -> float:
    """Return the two-sided p-value for discordant pair counts b and c."""
    if min(b, c) < 0:
        raise ValueError("Discordant counts must be non-negative")
    result = contingency_tables.mcnemar([[0, b], [c, 0]], exact=b + c < 25, correction=True)
    return float(result.pvalue)


def wilcoxon_paired(x: np.ndarray, y: np.ndarray) -> float:
    """Return the two-sided signed-rank p-value for paired observations in matching units."""
    if x.shape != y.shape or x.ndim != 1:
        raise ValueError("Expected paired one-dimensional arrays of equal length")
    if x.size and np.array_equal(x, y):
        return 1.0
    return float(stats.wilcoxon(x, y, alternative="two-sided").pvalue)


def kendall_tau_perm(a: list, b: list, n_perm: int, seed: int) -> tuple[float, float]:
    """Return tau-b and a two-sided p-value from seeded permutations of the pairings."""
    if len(a) != len(b) or n_perm < 1:
        raise ValueError("Expected equal-length rankings and at least one permutation")

    def tau(permuted: np.ndarray) -> float:
        return float(stats.kendalltau(a, permuted, method="asymptotic").statistic)

    observed = tau(np.asarray(b))
    if not np.isfinite(observed):
        return observed, float("nan")
    result = stats.permutation_test(
        (b,),
        tau,
        permutation_type="pairings",
        vectorized=False,
        n_resamples=n_perm,
        random_state=np.random.default_rng(seed),
    )
    return observed, float(result.pvalue)


def fisher_exact(table: list[list[int]]) -> float:
    """Return the two-sided Fisher exact p-value for a 2×2 table of counts."""
    if np.shape(table) != (2, 2):
        raise ValueError("Expected a 2×2 contingency table")
    return float(stats.fisher_exact(table, alternative="two-sided").pvalue)


def bootstrap_ci(
    values: np.ndarray,
    stat: Callable[[np.ndarray], float],
    n_resamples: int,
    seed: int,
    alpha: float = 0.05,
) -> tuple[float, float, float]:
    """Return the statistic and percentile bounds in its units, resampling rows.

    For operating-day inference, supply one row per day.
    """
    if values.ndim == 0 or n_resamples < 1 or not 0 < alpha < 1:
        raise ValueError("Expected a sample array, at least one resample and 0 < alpha < 1")
    if len(values) == 0:
        return (float("nan"),) * 3

    def statistic(indices: np.ndarray) -> float:
        return float(stat(values[indices]))

    indices = np.arange(len(values))
    point = statistic(indices)
    if len(values) == 1:
        return point, point, point
    result = stats.bootstrap(
        (indices,),
        statistic,
        vectorized=False,
        method="percentile",
        n_resamples=n_resamples,
        confidence_level=1 - alpha,
        random_state=np.random.default_rng(seed),
    )
    return point, float(result.confidence_interval.low), float(result.confidence_interval.high)
