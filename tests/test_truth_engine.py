"""UC-021: truth (validity) of linguistic summaries. Invariants I1 (analytical) and I2
(independent implementation: Simpful)."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from urban_computing.fuzzy.truth import fuzzy_proportion, truth_restricted, truth_simple
from urban_computing.fuzzy.vocabulary import Trapezoid, load_vocabulary

ROOT = Path(__file__).resolve().parents[1]
VOCAB = load_vocabulary(ROOT / "config" / "vocabulary.yaml")
CORE = VOCAB.quantifiers["core"]
MOST, FEW, HALF = CORE["most"], CORE["few"], CORE["about_half"]
SEED = 20261126  # config/study.yaml study.seed
TOL_I1 = 1e-9

# --------------------------------------------------------------------- I1 analytical


@pytest.mark.parametrize("n", [1, 7, 1000])
def test_i1_all_zero_and_all_one(n):
    zeros, ones = np.zeros(n), np.ones(n)
    assert fuzzy_proportion(zeros) == 0.0 and fuzzy_proportion(ones) == 1.0
    assert abs(truth_simple(zeros, MOST) - 0.0) < TOL_I1
    assert abs(truth_simple(zeros, FEW) - 1.0) < TOL_I1
    assert abs(truth_simple(ones, MOST) - 1.0) < TOL_I1
    assert abs(truth_simple(ones, FEW) - 0.0) < TOL_I1


def test_i1_eighty_percent_fully_late():
    # 80 % of rows fully "late", 20 % not at all -> p = 0.8; most = (0.8 - 0.5)/(0.85 - 0.5)
    late = VOCAB.summarizers["arrival_delay_minutes"]["late"]
    delays = np.array([6.0] * 80 + [0.0] * 20)
    mu = late(delays)
    assert fuzzy_proportion(mu) == pytest.approx(0.8, abs=TOL_I1)
    assert abs(truth_simple(mu, MOST) - (0.8 - 0.5) / (0.85 - 0.5)) < TOL_I1
    assert abs(truth_simple(mu, FEW) - 0.0) < TOL_I1


def test_i1_half_membership_rows():
    mu = np.full(10, 0.5)  # e.g. delay 2 min: on_time = slightly_late = 0.5
    assert abs(fuzzy_proportion(mu) - 0.5) < TOL_I1
    assert abs(truth_simple(mu, HALF) - 1.0) < TOL_I1
    assert abs(truth_simple(mu, MOST) - 0.0) < TOL_I1


@pytest.mark.parametrize("tnorm", ["product", "min"])
def test_i1_restricted_with_crisp_r(tnorm):
    mu_R = np.array([1, 1, 1, 1, 0, 0], dtype=float)  # e.g. "Monday morning" rows
    mu_S = np.array([1, 1, 1, 0, 1, 1], dtype=float)  # 3 of the 4 R rows are S
    assert abs(fuzzy_proportion(mu_S, mu_R, tnorm) - 0.75) < TOL_I1
    expected = (0.75 - 0.5) / (0.85 - 0.5)
    assert abs(truth_restricted(mu_R, mu_S, MOST, tnorm) - expected) < TOL_I1


def test_i1_restricted_fuzzy_r_tnorms_differ_as_defined():
    mu_R = np.array([0.5, 1.0])
    mu_S = np.array([0.4, 0.2])
    assert abs(fuzzy_proportion(mu_S, mu_R, "product") - (0.2 + 0.2) / 1.5) < TOL_I1
    assert abs(fuzzy_proportion(mu_S, mu_R, "min") - (0.4 + 0.2) / 1.5) < TOL_I1


def test_restricted_with_all_ones_r_equals_simple():
    rng = np.random.default_rng(SEED)
    mu_S = rng.random(500)
    assert abs(truth_restricted(np.ones(500), mu_S, MOST) - truth_simple(mu_S, MOST)) < TOL_I1


# --------------------------------------------------------------------- empty / missing


def test_empty_restriction_returns_nan():
    mu_S = np.array([1.0, 0.0])
    assert np.isnan(fuzzy_proportion(mu_S, np.zeros(2)))
    assert np.isnan(truth_restricted(np.zeros(2), mu_S, MOST))


def test_empty_input_returns_nan():
    assert np.isnan(fuzzy_proportion(np.array([])))
    assert np.isnan(truth_simple(np.array([]), MOST))


def test_nan_rows_are_dropped_not_counted():
    """UC-020 review carry-over: Trapezoid maps NaN (e.g. cancelled train) to NaN."""
    late = VOCAB.summarizers["arrival_delay_minutes"]["late"]
    delays = np.array([6.0, 6.0, 6.0, 6.0, 0.0, np.nan, np.nan])
    mu = late(delays)
    assert np.isnan(mu).sum() == 2
    assert fuzzy_proportion(mu) == pytest.approx(0.8)
    assert truth_simple(mu, MOST) == pytest.approx((0.8 - 0.5) / 0.35)
    assert np.isnan(fuzzy_proportion(np.array([np.nan, np.nan])))


def test_nan_in_restriction_or_summarizer_drops_the_pair():
    mu_R = np.array([1.0, 1.0, np.nan, 1.0])
    mu_S = np.array([1.0, np.nan, 1.0, 0.0])
    # only rows 0 and 3 are complete -> 1 / 2
    assert fuzzy_proportion(mu_S, mu_R) == pytest.approx(0.5)


@pytest.mark.parametrize(
    "bad", [np.array([0.2, 1.5]), np.array([-0.1, 0.3]), np.array([np.inf, 0.0])]
)
def test_out_of_range_memberships_raise(bad):
    with pytest.raises(ValueError):
        fuzzy_proportion(bad)
    with pytest.raises(ValueError):
        truth_restricted(bad, np.zeros(2), MOST)


def test_shape_mismatch_and_bad_tnorm_raise():
    with pytest.raises(ValueError):
        fuzzy_proportion(np.zeros(3), np.zeros(2))
    with pytest.raises(ValueError):
        fuzzy_proportion(np.zeros(2), np.zeros(2), tnorm="lukasiewicz")  # type: ignore[arg-type]


def test_returns_python_float():
    assert type(truth_simple(np.ones(3), MOST)) is float
    assert type(fuzzy_proportion(np.ones(3))) is float


# --------------------------------------------------------------------- properties


def test_property_truth_in_unit_interval():
    rng = np.random.default_rng(SEED)
    for _ in range(300):
        n = int(rng.integers(1, 200))
        mu_S, mu_R = rng.random(n), rng.random(n)
        mu_R[rng.random(n) < 0.3] = 0.0
        for q in (*CORE.values(), *VOCAB.quantifiers["extended"].values()):
            for v in (truth_simple(mu_S, q), truth_restricted(mu_R, mu_S, q)):
                assert np.isnan(v) or 0.0 <= v <= 1.0


@pytest.mark.parametrize("q", ["most", "almost_all"])
def test_property_adding_satisfying_rows_never_lowers_monotone_q(q):
    Q = CORE.get(q) or VOCAB.quantifiers["extended"][q]
    rng = np.random.default_rng(SEED)
    for _ in range(300):
        mu_S = rng.random(int(rng.integers(1, 100)))
        mu_R = rng.random(mu_S.size)
        more = int(rng.integers(1, 20))
        before_s = truth_simple(mu_S, Q)
        after_s = truth_simple(np.concatenate([mu_S, np.ones(more)]), Q)
        assert after_s >= before_s - 1e-12
        for tnorm in ("product", "min"):
            before_r = truth_restricted(mu_R, mu_S, Q, tnorm)
            r_new = rng.random(more) * 0.9 + 0.1  # rows in R (degree > 0) fully satisfying S
            after_r = truth_restricted(
                np.concatenate([mu_R, r_new]), np.concatenate([mu_S, np.ones(more)]), Q, tnorm
            )
            if not np.isnan(before_r):
                assert after_r >= before_r - 1e-12


# --------------------------------------------------------------------- I2 Simpful


def _simpful_equivalent(t: Trapezoid):
    """Simpful Trapezoidal_MF for our Trapezoid. Simpful encodes an open left shoulder as
    a == b (membership 1 below b) and an open right shoulder as c == d."""
    simpful = pytest.importorskip("simpful")
    if t.a is None:
        return simpful.Trapezoidal_MF(a=t.c, b=t.c, c=t.c, d=t.d)
    if t.c is None:
        return simpful.Trapezoidal_MF(a=t.a, b=t.b, c=t.b, d=t.b)
    return simpful.Trapezoidal_MF(a=t.a, b=t.b, c=t.c, d=t.d)


WORDS = [
    (f"summarizers.{attr}.{w}", fn, (-5.0, 30.0))
    for attr, words in VOCAB.summarizers.items()
    for w, fn in words.items()
] + [
    (f"quantifiers.{s}.{w}", fn, (0.0, 1.0))
    for s, words in VOCAB.quantifiers.items()
    for w, fn in words.items()
]


@pytest.mark.parametrize("name,fn,domain", WORDS, ids=[w[0] for w in WORDS])
def test_i2_membership_matches_simpful(name, fn, domain):
    mf = _simpful_equivalent(fn)
    grid = np.linspace(*domain, 10_000)
    ours = fn(grid)
    theirs = np.array([mf(float(x)) for x in grid])
    assert np.max(np.abs(ours - theirs)) < 1e-6, name


def test_i2_truth_matches_simpful_pipeline():
    """Truth from Simpful memberships (pure Python loop) equals the NumPy engine."""
    rng = np.random.default_rng(SEED)
    delays = rng.normal(2.0, 4.0, 2_000)
    late = VOCAB.summarizers["arrival_delay_minutes"]["late"]
    on_time = VOCAB.summarizers["arrival_delay_minutes"]["on_time"]
    late_sf, on_time_sf, most_sf = (_simpful_equivalent(t) for t in (late, on_time, MOST))
    mu_S = [late_sf(float(x)) for x in delays]
    mu_R = [on_time_sf(float(x)) for x in delays]
    p_simple = sum(mu_S) / len(mu_S)
    p_restr = sum(r * s for r, s in zip(mu_R, mu_S, strict=True)) / sum(mu_R)
    assert abs(truth_simple(late(delays), MOST) - most_sf(p_simple)) < 1e-9
    assert abs(truth_restricted(on_time(delays), late(delays), MOST) - most_sf(p_restr)) < 1e-9


# --------------------------------------------------------------------- performance


def test_ten_million_rows_under_two_seconds():
    rng = np.random.default_rng(SEED)
    mu_S, mu_R = rng.random(10_000_000), rng.random(10_000_000)
    truth_simple(mu_S[:10], MOST)  # warm-up
    t0 = time.perf_counter()
    truth_simple(mu_S, MOST)
    truth_restricted(mu_R, mu_S, MOST, "product")
    truth_restricted(mu_R, mu_S, MOST, "min")
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, f"{elapsed:.2f} s for 3 x 10M-row evaluations"
