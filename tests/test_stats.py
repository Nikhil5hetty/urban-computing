"""Reference and edge cases for the evaluation statistics wrappers."""

import numpy as np
import pytest

from urban_computing.evaluation.stats import (
    bootstrap_ci,
    fisher_exact,
    kendall_tau_perm,
    mcnemar,
    wilcoxon_paired,
    wilson_ci,
)


def test_wilson_reference():
    # statsmodels proportion_confint, method="wilson", 5 successes in 10 trials.
    assert wilson_ci(5, 10) == pytest.approx((0.5, 0.2365930905, 0.7634069095))
    assert wilson_ci(0, 10)[1] == pytest.approx(0)
    assert np.isnan(wilson_ci(0, 0)).all()


def test_mcnemar_reference():
    # statsmodels contingency_tables.mcnemar reference values in both documented modes.
    assert mcnemar(3, 9) == pytest.approx(0.14599609375)
    assert mcnemar(5, 20) == pytest.approx(0.00511026066)
    assert mcnemar(0, 0) == 1.0


def test_kendall_reference_and_seed():
    # SciPy kendalltau documentation (liver measurements), with exhaustive permutation.
    x = [7.1, 7.1, 7.2, 8.3, 9.4, 10.5, 11.4]
    y = [2.8, 2.9, 2.8, 2.6, 3.5, 4.6, 5.0]
    assert kendall_tau_perm(x, y, 5040, 42) == pytest.approx((0.55, 0.12222222222222222))
    assert kendall_tau_perm(x, y, 37, 42) == kendall_tau_perm(x, y, 37, 42)
    assert np.isnan(kendall_tau_perm([1, 1], [2, 3], 10, 42)).all()


def test_fisher_and_wilcoxon():
    assert fisher_exact([[6, 2], [1, 4]]) == pytest.approx(0.102564102564)
    x = np.array([1, 2, 3, 4, 5])
    assert wilcoxon_paired(x, np.zeros_like(x)) == pytest.approx(0.0625)
    assert wilcoxon_paired(x, x) == 1.0


def test_bootstrap_resamples_whole_rows():
    values = np.array([[1, 2], [10, 20], [100, 200]])

    def stat(rows):
        assert np.array_equal(rows[:, 1], rows[:, 0] * 2)
        return rows[:, 0].mean()

    result = bootstrap_ci(values, stat, 500, 42)
    assert result == bootstrap_ci(values, stat, 500, 42)
    point, low, high = result
    assert point == 37
    assert low < point < high
    assert bootstrap_ci(values[:1], stat, 500, 42) == (1, 1, 1)
