"""UC-020: membership functions and vocabulary loading (offline, synthetic inputs only)."""

from __future__ import annotations

import ast
import copy
from pathlib import Path

import numpy as np
import pytest
import yaml

from urban_computing.fuzzy.vocabulary import (
    Trapezoid,
    Vocabulary,
    load_vocabulary,
    vocabulary_from_dict,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "vocabulary.yaml"
DELAYS = np.linspace(-5.0, 30.0, 3501)  # 0.01-min grid over the ticket's Ruspini range


@pytest.fixture(scope="module")
def vocab() -> Vocabulary:
    return load_vocabulary(CONFIG)


@pytest.fixture()
def raw() -> dict:
    return yaml.safe_load(CONFIG.read_text())


# --------------------------------------------------------------------- Trapezoid shape


def test_trapezoid_zero_at_a_and_d_one_on_core_linear_between():
    t = Trapezoid(1.0, 3.0, 5.0, 9.0)
    x = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 9.0, 10.0])
    np.testing.assert_array_equal(t(x), [0.0, 0.0, 0.5, 1.0, 1.0, 1.0, 0.5, 0.0, 0.0])
    # linear: equal steps give equal increments on both slopes
    rise = t(np.linspace(1.0, 3.0, 5))
    fall = t(np.linspace(5.0, 9.0, 5))
    np.testing.assert_allclose(np.diff(rise), 0.25)
    np.testing.assert_allclose(np.diff(fall), -0.25)


def test_triangle_and_open_shoulders():
    tri = Trapezoid(1.0, 3.0, 3.0, 5.0)
    np.testing.assert_array_equal(tri(np.array([1.0, 2.0, 3.0, 4.0, 5.0])), [0, 0.5, 1, 0.5, 0])
    left = Trapezoid(None, None, 1.0, 3.0)
    np.testing.assert_array_equal(left(np.array([-1e9, 1.0, 2.0, 3.0])), [1, 1, 0.5, 0])
    right = Trapezoid(8.0, 10.0, None, None)
    np.testing.assert_array_equal(right(np.array([8.0, 9.0, 10.0, 1e9])), [0, 0.5, 1, 1])


def test_vertical_edges_are_crisp_steps():
    step = Trapezoid(2.0, 2.0, None, None)
    np.testing.assert_array_equal(step(np.array([1.99, 2.0, 2.01])), [0, 1, 1])


def test_output_shape_dtype_range_and_nan():
    t = Trapezoid(0.0, 1.0, 2.0, 3.0)
    x = np.array([[0.5, np.nan], [2.5, 10.0]])
    y = t(x)
    assert y.shape == x.shape and y.dtype == np.float64
    assert np.isnan(y[0, 1])
    finite = y[~np.isnan(y)]
    assert ((finite >= 0) & (finite <= 1)).all()
    assert t(np.float64(0.5)).shape == ()  # scalars work too


@pytest.mark.parametrize(
    "abcd",
    [
        (3.0, 1.0, 4.0, 5.0),  # a > b
        (0.0, 2.0, 1.0, 3.0),  # b > c
        (0.0, 1.0, 3.0, 2.0),  # c > d
        (None, 1.0, 2.0, 3.0),  # half-open left shoulder
        (0.0, 1.0, None, 3.0),  # half-open right shoulder
        (None, None, None, None),  # constant 1 is not a word
        (0.0, float("nan"), 1.0, 2.0),
    ],
)
def test_invalid_trapezoid_raises(abcd):
    with pytest.raises(ValueError):
        Trapezoid(*abcd)


# --------------------------------------------------------------------- loaded vocabulary


def test_loads_all_groups_from_config(vocab, raw):
    assert set(vocab.summarizers) == set(raw["summarizers"])
    assert set(vocab.quantifiers) == set(raw["quantifiers"])
    for attr, words in raw["summarizers"].items():
        for word, abcd in words.items():
            assert vocab.summarizers[attr][word] == Trapezoid(*abcd)
    assert vocab.quantifiers["core"].keys() == {"few", "about_half", "most"}
    assert vocab.decision_words == ("safe", "at_risk", "risky")
    assert (
        vocab.perception_spread_min == raw["perception"]["late_for_my_transfer"]["spread_minutes"]
    )


def test_on_time_reaches_zero_at_sbb_three_minutes(vocab):
    on_time = vocab.summarizers["arrival_delay_minutes"]["on_time"]
    assert on_time(np.array(3.0)) == 0.0  # D-007: comparable with the crisp 3-min rule
    assert on_time(np.array(2.999)) > 0.0


def test_most_is_monotone_non_decreasing(vocab):
    p = np.linspace(0.0, 1.0, 1001)
    for q in ("most",):
        assert (np.diff(vocab.quantifiers["core"][q](p)) >= 0).all()
    assert (np.diff(vocab.quantifiers["extended"]["almost_all"](p)) >= 0).all()
    assert (np.diff(vocab.quantifiers["core"]["few"](p)) <= 0).all()


@pytest.mark.parametrize("attr", ["arrival_delay_minutes", "connection_slack_minutes"])
def test_summarizer_words_form_ruspini_partition(vocab, attr):
    total = sum(fn(DELAYS) for fn in vocab.summarizers[attr].values())
    assert total.min() >= 0.99 and total.max() <= 1.01, (total.min(), total.max())


# --------------------------------------------------------------------- perception


@pytest.mark.parametrize("margin", [2.0, 4.0, 7.5])
def test_late_for_my_transfer(vocab, margin):
    spread = vocab.perception_spread_min
    fn = vocab.late_for_my_transfer(margin)
    x = np.linspace(-5.0, 30.0, 3501)
    y = fn(x)
    assert (y[x <= margin - spread] == 0).all()
    assert (y[x >= margin] == 1).all()
    assert (np.diff(y) >= 0).all()
    assert fn(np.array(margin - spread / 2)) == pytest.approx(0.5)


def test_late_for_my_transfer_spread_override_and_crisp_limit(vocab):
    fn = vocab.late_for_my_transfer(4.0, spread_min=1.0)
    assert fn(np.array(3.5)) == pytest.approx(0.5)
    crisp = vocab.late_for_my_transfer(4.0, spread_min=0.0)
    np.testing.assert_array_equal(crisp(np.array([3.99, 4.0])), [0.0, 1.0])
    with pytest.raises(ValueError):
        vocab.late_for_my_transfer(4.0, spread_min=-1.0)


# --------------------------------------------------------------------- config validation


def test_config_change_needs_no_code_change(raw):
    raw["summarizers"]["walk_minutes"] = {"short": [None, None, 2, 4], "long": [2, 4, None, None]}
    raw["quantifiers"]["core"]["most"] = [0.6, 0.9, None, None]
    raw["perception"]["late_for_my_transfer"]["spread_minutes"] = 3
    v = vocabulary_from_dict(raw)
    assert v.summarizers["walk_minutes"]["long"](np.array(3.0)) == 0.5
    assert v.quantifiers["core"]["most"](np.array(0.75)) == pytest.approx(0.5)
    assert v.late_for_my_transfer(5.0)(np.array(3.5)) == pytest.approx(0.5)


def test_load_vocabulary_reads_any_path(tmp_path, raw):
    raw["perception"]["late_for_my_transfer"]["spread_minutes"] = 1.5
    p = tmp_path / "vocab.yaml"
    p.write_text(yaml.safe_dump(raw))
    assert load_vocabulary(p).perception_spread_min == 1.5


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c["summarizers"]["arrival_delay_minutes"].__setitem__("late", [6, 5, 8, 10]),
        lambda c: c["summarizers"]["arrival_delay_minutes"].__setitem__("late", [3, 5, 8]),
        lambda c: c["quantifiers"]["core"].__setitem__("most", [0.5, 1.2, None, None]),
        lambda c: c["perception"]["late_for_my_transfer"].__setitem__("spread_minutes", -1),
        lambda c: c.pop("quantifiers"),
        lambda c: c.__setitem__("decision_words", []),
        lambda c: c["summarizers"].__setitem__("empty_attr", {}),
    ],
)
def test_invalid_config_raises_value_error(raw, mutate):
    cfg = copy.deepcopy(raw)
    mutate(cfg)
    with pytest.raises(ValueError):
        vocabulary_from_dict(cfg)


# --------------------------------------------------------------------- purity (AGENTS §4.9)


def test_fuzzy_package_has_no_pandas_or_duckdb_imports():
    banned = {"pandas", "duckdb", "polars", "pyarrow"}
    for path in (ROOT / "src" / "urban_computing" / "fuzzy").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for n in names:
                assert n.split(".")[0] not in banned, f"{path.name} imports {n}"
