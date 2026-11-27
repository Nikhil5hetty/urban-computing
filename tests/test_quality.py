"""UC-022: Hudec coverage, Qc and regional quality (docs/methods.md §3, D-027)."""

from __future__ import annotations

import ast
import inspect
import math
from pathlib import Path

import numpy as np
import pytest
import yaml

from urban_computing.fuzzy import quality
from urban_computing.fuzzy.quality import (
    DEFAULT_COVERAGE,
    coverage,
    coverage_from_ratio,
    included_ratio,
    ordinal_sum,
    quality_qc,
    regional_quality,
)

ROOT = Path(__file__).resolve().parents[1]
MINING = yaml.safe_load((ROOT / "config" / "study.yaml").read_text())["mining"]


def records(n: int, m: int, mu: float = 0.7) -> tuple[np.ndarray, np.ndarray]:
    """n records of which m have mu_R > 0 and mu_S > 0 (the rest have mu_S = 0)."""
    mu_r = np.full(n, 0.9)
    mu_s = np.zeros(n)
    mu_s[:m] = mu
    return mu_r, mu_s


# --------------------------------------------------------------------- coverage §3.1


@pytest.mark.parametrize("m,i_c,c", [(175, 0.0875, 0.5377), (320, 0.16, 1.0), (13, 0.0065, 0.0)])
def test_hudec2022_table2_worked_example(m, i_c, c):
    """hudec2022 Table 2, p. 332: n = 2000, r1 = 0.02, r2 = 0.15."""
    mu_r, mu_s = records(2000, m)
    assert included_ratio(mu_r, mu_s) == pytest.approx(i_c)
    assert coverage(mu_r, mu_s, MINING) == pytest.approx(c, abs=5e-5)


def test_coverage_piecewise_branches_and_continuity():
    r1, r2 = 0.02, 0.15
    mid = (r1 + r2) / 2
    f = lambda x: coverage_from_ratio(x, r1, r2)  # noqa: E731
    assert f(0.0) == 0.0 and f(r1) == 0.0 and f(r2) == 1.0 and f(1.0) == 1.0
    assert f(mid) == pytest.approx(0.5)  # both middle branches give 0.5 at the midpoint
    assert f(mid - 1e-12) == pytest.approx(0.5) and f(mid + 1e-12) == pytest.approx(0.5)
    xs = np.linspace(0, 0.3, 3001)
    ys = np.array([f(x) for x in xs])
    assert (np.diff(ys) >= -1e-15).all()  # monotone non-decreasing
    x = 0.05  # first middle branch: 2 (x - r1)^2 / (r2 - r1)^2
    assert f(x) == pytest.approx(2 * (x - r1) ** 2 / (r2 - r1) ** 2)
    x = 0.12  # second middle branch: 1 - 2 (r2 - x)^2 / (r2 - r1)^2
    assert f(x) == pytest.approx(1 - 2 * (r2 - x) ** 2 / (r2 - r1) ** 2)


def test_coverage_counts_crisp_support_over_all_records():
    # m_i = 1 iff mu_S > 0 AND mu_R > 0; any degree above 0 counts; n = all records
    mu_r = np.array([0.0, 0.01, 1.0, 0.5, 0.2])
    mu_s = np.array([1.0, 0.01, 0.0, 0.3, 1.0])
    assert included_ratio(mu_r, mu_s) == pytest.approx(3 / 5)
    assert included_ratio(None, mu_s) == pytest.approx(4 / 5)  # support of S (not used for Qc)


def test_coverage_edge_cases():
    n = 1000
    assert coverage(np.zeros(n), np.ones(n), MINING) == 0.0  # no rows in R
    assert coverage(np.ones(n), np.ones(n), MINING) == 1.0  # all rows in R and S
    assert math.isnan(coverage(np.array([]), np.array([]), MINING))
    # NaN = missing record: dropped like in the truth engine (methods §2)
    mu_r, mu_s = records(2000, 175)
    mu_s = np.concatenate([mu_s, [np.nan] * 50])
    mu_r = np.concatenate([mu_r, [1.0] * 50])
    assert coverage(mu_r, mu_s, MINING) == pytest.approx(0.5377, abs=5e-5)


def test_coverage_reads_mining_config():
    assert (MINING["coverage_r1"], MINING["coverage_r2"]) == (0.02, 0.15)
    assert DEFAULT_COVERAGE == {"coverage_r1": 0.02, "coverage_r2": 0.15}
    mu_r, mu_s = records(2000, 240)  # i_C = 0.12
    assert coverage(mu_r, mu_s, MINING) < 1.0
    assert coverage(mu_r, mu_s, {**MINING, "coverage_r2": 0.10}) == 1.0  # UC-054 sensitivity
    assert coverage(mu_r, mu_s, {"mining": MINING}) == coverage(mu_r, mu_s, MINING)
    assert coverage(mu_r, mu_s) == coverage(mu_r, mu_s, MINING)  # defaults = D-027 values


@pytest.mark.parametrize("bad", [{"coverage_r1": 0.2, "coverage_r2": 0.1},
                                 {"coverage_r1": -0.1, "coverage_r2": 0.1},
                                 {"coverage_r1": 0.1, "coverage_r2": 1.5}])  # fmt: skip
def test_invalid_coverage_params_raise(bad):
    with pytest.raises(ValueError):
        coverage(np.ones(3), np.ones(3), bad)


def test_out_of_range_memberships_raise():
    with pytest.raises(ValueError):
        coverage(np.array([1.2]), np.array([0.5]), MINING)
    with pytest.raises(ValueError):
        coverage(np.array([1.0, 1.0]), np.array([0.5]), MINING)


# --------------------------------------------------------------------- Qc §3.2


def test_qc_zero_below_c_min_and_product_otherwise():
    assert quality_qc(1.0, 0.0) == 0.0  # hudec2018 p. 997: v = 1, C = 0 -> not representative
    assert quality_qc(0.9, 0.4999) == 0.0
    assert quality_qc(0.9, 0.5) == pytest.approx(0.45)  # C >= c_min uses t(v, C)
    assert quality_qc(0.814, 1.0) == pytest.approx(0.814)


def test_qc_le_truth_for_product():
    rng = np.random.default_rng(20261126)
    for v, c in rng.random((2000, 2)):
        q = quality_qc(float(v), float(c))
        assert 0.0 <= q <= v and (q == 0.0 or c >= 0.5)


def test_qc_is_nonidempotent_product_only():
    """hudec2018 Eq. (9) needs a nonidempotent t-norm: min (the truth ablation) is refused."""
    assert MINING["qc_tnorm"] == "product"
    with pytest.raises(ValueError, match="nonidempotent"):
        quality_qc(0.9, 0.9, tnorm="min")
    assert quality_qc(0.9, 0.8, c_min=0.85) == 0.0  # c_min parameter honoured


def test_qc_missing_values():
    assert math.isnan(quality_qc(float("nan"), 0.9))
    assert math.isnan(quality_qc(0.9, float("nan")))
    with pytest.raises(ValueError):
        quality_qc(1.2, 0.9)


# --------------------------------------------------------------------- regional quality §3.3


def test_hudec2022_districts_worked_example():
    """hudec2022 Table 1 (p. 327) and results (p. 331): N = 21, 770, 450."""
    truths = {"D1": 0.7143, "D2": 0.7013, "D3": 0.0}
    sizes = {"D1": 21, "D2": 770, "D3": 450}
    a = regional_quality(truths, sizes)
    assert set(a) == {"D1", "D2", "D3"}
    assert a["D1"] == pytest.approx(0.2416, abs=1e-4)  # printed 0.2413 (rounded inputs)
    assert a["D2"] == pytest.approx(1.0)
    assert a["D3"] == 0.0  # v_i = 0 rule (pp. 329, 331); Eq. (16) alone would give 0.084
    assert ordinal_sum(0.0, 450 / 770) == pytest.approx(0.084, abs=1e-3)  # why the rule exists


def test_ordinal_sum_paper_value_and_pieces():
    assert ordinal_sum(1.0, 0.001) == pytest.approx(0.501)  # p. 331
    # A1 on [0, 0.5]^2: rescaled product 2xy (Eq. (14))
    assert ordinal_sum(0.2, 0.3) == pytest.approx(2 * 0.2 * 0.3)
    # A2 on [0.5, 1]^2: rescaled probabilistic sum (Eq. (15))
    assert ordinal_sum(0.7, 0.9) == pytest.approx(-1 + 2 * 0.7 + 2 * 0.9 - 2 * 0.7 * 0.9)
    # mixed regions: arithmetic-mean form x + y - 1/2 (Eq. (16))
    assert ordinal_sum(0.8, 0.1) == pytest.approx(0.8 + 0.1 - 0.5)
    assert ordinal_sum(0.3, 0.9) == pytest.approx(0.3 + 0.9 - 0.5)


def test_ordinal_sum_properties():
    g = np.linspace(0, 1, 41)
    for x in g:
        for y in g:
            v = ordinal_sum(float(x), float(y))
            assert -1e-12 <= v <= 1 + 1e-12
            assert v == pytest.approx(ordinal_sum(float(y), float(x)))  # symmetric
    for x in g:  # monotone in both arguments
        col = [ordinal_sum(float(x), float(y)) for y in g]
        assert all(b >= a - 1e-12 for a, b in zip(col, col[1:], strict=False))
    assert ordinal_sum(0.5, 0.7) == pytest.approx(0.7)  # a = 0.5 is the neutral element


def test_regional_quality_proportions_and_edge_cases():
    a = regional_quality({"big": 0.8, "small": 0.8}, {"big": 1000, "small": 10})
    assert a["big"] == pytest.approx(ordinal_sum(0.8, 1.0))
    assert a["small"] == pytest.approx(ordinal_sum(0.8, 0.01))  # p_i = N_i / max N
    assert a["small"] < a["big"]
    assert math.isnan(regional_quality({"r": float("nan")}, {"r": 5})["r"])
    with pytest.raises(ValueError):
        regional_quality({"a": 0.5}, {"b": 5})  # regions differ
    with pytest.raises(ValueError):
        regional_quality({"a": 0.5}, {"a": 0})  # no records anywhere
    with pytest.raises(ValueError):
        regional_quality({"a": 0.5}, {"a": -3})


# --------------------------------------------------------------------- docs / purity


def test_docstrings_cite_the_equations():
    assert "Eq. (A.3)" in included_ratio.__doc__ and "Eq. (18)" in included_ratio.__doc__
    assert "Eq. (A.4)" in coverage_from_ratio.__doc__ and "Eq. (19)" in coverage_from_ratio.__doc__
    assert "Eq. (9)" in quality_qc.__doc__
    assert "Eq. (13)" in ordinal_sum.__doc__ and "Eq. (16)" in ordinal_sum.__doc__
    assert "Eq. (8)" in regional_quality.__doc__


def test_fuzzy_quality_is_pure_numpy():
    tree = ast.parse(inspect.getsource(quality))
    mods = {
        (n.module or "") if isinstance(n, ast.ImportFrom) else a.name
        for n in ast.walk(tree)
        if isinstance(n, (ast.Import, ast.ImportFrom))
        for a in (n.names if isinstance(n, ast.Import) else [None])
    }
    assert not {m.split(".")[0] for m in mods if m} & {"pandas", "duckdb", "yaml", "pathlib"}


# --------------------------------------------------------------------- review #54


def test_unrestricted_summary_has_full_coverage_and_keeps_qc():
    """hudec2018 p. 987: basic summaries cover the whole data set (C = 1)."""
    mu_s = np.zeros(1000)
    mu_s[:50] = 1.0  # "few trains are very late": 50 of 1000 very late
    c = coverage(None, mu_s, MINING)
    assert c == 1.0
    assert quality_qc(1.0, c) == 1.0 and quality_qc(0.6, c) == pytest.approx(0.6)  # Qc = v
    assert coverage(None, np.zeros(10), MINING) == 1.0  # even if no record is S
    assert math.isnan(coverage(None, np.array([np.nan, np.nan]), MINING))
    assert math.isnan(coverage(None, np.array([]), MINING))
    # the restricted case is unchanged
    mu_r, mu_s = records(2000, 175)
    assert coverage(mu_r, mu_s, MINING) == pytest.approx(0.5377, abs=5e-5)


@pytest.mark.parametrize("a", [0.1, 0.25, 0.4, 0.5, 0.6, 0.9])
def test_general_ordinal_sum_stays_in_unit_square(a):
    assert ordinal_sum(0.0, 0.0, a=a) == pytest.approx(0.0, abs=1e-12)
    assert ordinal_sum(1.0, 1.0, a=a) == pytest.approx(1.0)
    g = np.linspace(0, 1, 21)
    vals = [ordinal_sum(float(x), float(y), a=a) for x in g for y in g]
    assert min(vals) >= -1e-12 and max(vals) <= 1 + 1e-12
    assert ordinal_sum(a, 0.7, a=a) == pytest.approx(0.7)  # a is neutral
    # pieces: xy / a below a, a + (1 - a) S(u, v) above a
    lo = a / 2
    assert ordinal_sum(lo, lo, a=a) == pytest.approx(lo * lo / a)
    hi = (1 + a) / 2
    u = (hi - a) / (1 - a)
    assert ordinal_sum(hi, hi, a=a) == pytest.approx(a + (1 - a) * (2 * u - u * u))


def test_general_form_equals_paper_form_at_one_half():
    for x in np.linspace(0, 1, 11):
        for y in np.linspace(0, 1, 11):
            lo_x, lo_y, hi_x, hi_y = min(0.5, x), min(0.5, y), max(0.5, x), max(0.5, y)
            paper = 2 * lo_x * lo_y + (-1 + 2 * hi_x + 2 * hi_y - 2 * hi_x * hi_y) - 0.5
            assert ordinal_sum(float(x), float(y)) == pytest.approx(paper)
    with pytest.raises(ValueError):
        ordinal_sum(0.3, 0.3, a=0.0)
    with pytest.raises(ValueError):
        ordinal_sum(0.3, 0.3, a=1.0)
