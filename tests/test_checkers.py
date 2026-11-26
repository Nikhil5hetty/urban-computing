"""UC-042: crisp (Stat-to-Text style) and fuzzy claim checkers on synthetic segments."""

from __future__ import annotations

import ast
import time
from pathlib import Path

import numpy as np
import pytest
import yaml

from urban_computing.fuzzy.vocabulary import load_vocabulary
from urban_computing.llm.checkers import (
    CRISP_DEFAULTS,
    CheckResult,
    check,
    crisp_intervals,
    crisp_quantifier,
)
from urban_computing.llm.parser import Claim

ROOT = Path(__file__).resolve().parents[1]
VOCAB = load_vocabulary(ROOT / "config" / "vocabulary.yaml")
CONFIG = yaml.safe_load((ROOT / "config" / "study.yaml").read_text())
D, C = "arrival_delay_minutes", "connection_slack_minutes"


def claim(q, s, r=None, status="ok", slot=0):
    return Claim(question_id="q1", slot=slot, quantifier=q, summarizer=s, restriction=r,
                 status=status)  # fmt: skip


def delays(*groups):
    """delays((52, 6.0), (48, 0.0)) -> 52 rows of 6 min and 48 rows of 0 min."""
    return {D: np.concatenate([np.full(n, v, dtype=float) for n, v in groups])}


# --------------------------------------------------------------------- acceptance


def test_borderline_52_percent_late_crisp_true_fuzzy_false():
    values = delays((52, 6.0), (48, 0.0))  # 6 min: fully "late" (fuzzy and crisp)
    r = check(claim("most", f"{D}:late"), values, VOCAB, CONFIG)
    assert r.crisp is True  # 0.52 > 0.5 (Stat-to-Text "more than half")
    assert r.fuzzy is not None and r.fuzzy < 0.5  # mu_most(0.52) = 0.02 / 0.35
    assert r.fuzzy == pytest.approx((0.52 - 0.5) / 0.35)
    assert r.fuzzy_true is False
    assert r.disagreement == "crisp_true_fuzzy_false"
    assert (r.n, r.p_crisp, r.p_fuzzy) == (100, pytest.approx(0.52), pytest.approx(0.52))


def test_crisp_false_fuzzy_true_case():
    # 2-min delays: crisp on time (< 3 min, D-007), fuzzy on_time only 0.5 each
    values = delays((60, 2.0), (40, 6.0))
    r = check(claim("about_half", f"{D}:on_time"), values, VOCAB, CONFIG)
    assert r.p_crisp == pytest.approx(0.6) and r.crisp is True  # |0.6 - 0.5| <= 0.1
    assert r.p_fuzzy == pytest.approx(0.3)
    assert r.fuzzy == pytest.approx(0.0) and r.disagreement == "crisp_true_fuzzy_false"
    values = delays((30, 0.0), (40, 1.0), (30, 2.0))  # p_crisp = 1.0, p_fuzzy = 0.85
    r = check(claim("about_half", f"{D}:on_time"), values, VOCAB, CONFIG)
    assert r.crisp is False and r.fuzzy_true is False and r.disagreement == "none"
    values = delays((10, 2.0), (90, 0.5))  # crisp few false? p_crisp = 1.0
    r = check(claim("most", f"{D}:on_time"), values, VOCAB, CONFIG)
    assert r.crisp is True and r.fuzzy_true is True and r.disagreement == "none"
    # crisp false, fuzzy true: "few are late" with many 3-4 min delays
    values = delays((30, 3.5), (70, 0.0))  # crisp: 3.5 is slightly_late, not late
    r = check(claim("about_half", f"{D}:slightly_late"), values, VOCAB, CONFIG)
    assert r.p_crisp == pytest.approx(0.3) and r.crisp is False
    assert r.p_fuzzy == pytest.approx(0.3 * 0.75 + 0.0)  # slightly_late(3.5) = 0.75
    values = delays((45, 2.0), (55, 0.0))
    r = check(claim("most", f"{D}:slightly_late"), values, VOCAB, CONFIG)
    assert r.crisp is False and r.fuzzy_true is False
    values = delays((80, 2.5), (20, 0.0))  # crisp slightly_late share 0; fuzzy 0.8 * 0.75
    r = check(claim("about_half", f"{D}:slightly_late"), values, VOCAB, CONFIG)
    assert r.crisp is False and r.p_fuzzy == pytest.approx(0.6)
    assert r.fuzzy_true is True and r.disagreement == "crisp_false_fuzzy_true"


def test_every_crisp_threshold_documented_in_methods_section_6():
    methods = (ROOT / "docs" / "methods.md").read_text()
    sec6 = methods[methods.index("## 6. Claim checkers") :]
    for token in ("> 0.5", "< 0.25", "≤ 0.1", "< 3", "4", "9", "< 0", "1.5", "≥ 0.5", "D-012",
                  "D-007"):  # fmt: skip
        assert token in sec6, token
    for attr, words in crisp_intervals(VOCAB, CONFIG).items():
        for word in words:
            assert f"`{word}`" in sec6, (attr, word)


def test_ten_thousand_claims_under_five_seconds():
    rng = np.random.default_rng(CONFIG["study"]["seed"])
    n = 1_000
    values = {
        D: rng.normal(2.0, 4.0, n),
        C: rng.normal(3.0, 3.0, n),
        "time_band": rng.choice(["morning_peak", "midday", "evening_peak"], n),
        "weekday": rng.integers(0, 7, n),
    }
    words = [(q, f"{a}:{w}") for q in ("few", "about_half", "most")
             for a, ws in VOCAB.summarizers.items() for w in ws]  # fmt: skip
    rs = [None, "time_band=morning_peak", "time_band=midday&weekday_group=monday"]
    claims = [claim(*words[i % len(words)], rs[i % 3], slot=i) for i in range(10_000)]
    t0 = time.perf_counter()
    results = [check(c, values, VOCAB, CONFIG) for c in claims]
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"{elapsed:.2f} s"
    assert all(r.disagreement != "n/a" for r in results)


def test_checkers_are_pure():
    src = (ROOT / "src" / "urban_computing" / "llm" / "checkers.py").read_text()
    tree = ast.parse(src)
    mods = {
        (n.module or "").split(".")[0] if isinstance(n, ast.ImportFrom) else a.name.split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, (ast.Import, ast.ImportFrom))
        for a in (n.names if isinstance(n, ast.Import) else [None])
    }
    assert not mods & {"pandas", "duckdb", "yaml", "random", "os", "pathlib", "io"}
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name)}  # fmt: skip
    assert "open" not in calls and "print" not in calls
    values = delays((52, 6.0), (48, 0.0))
    before = values[D].copy()
    assert check(claim("most", f"{D}:late"), values, VOCAB, CONFIG) == check(
        claim("most", f"{D}:late"), values, VOCAB, CONFIG
    )
    np.testing.assert_array_equal(values[D], before)  # input not mutated


# --------------------------------------------------------------------- crisp definitions


def test_crisp_intervals_follow_sbb_rule_and_midpoints():
    iv = crisp_intervals(VOCAB, CONFIG)
    assert iv[D] == {
        "on_time": (-np.inf, 3.0),  # SBB: < 3 min late is punctual (D-007)
        "slightly_late": (3.0, 4.0),  # midpoint of the 3..5 ramp
        "late": (4.0, 9.0),  # midpoint of the 8..10 ramp
        "very_late": (9.0, np.inf),
    }
    assert iv[C] == {
        "missed": (-np.inf, 0.0),  # slack < 0: transfer impossible (definition)
        "tight": (0.0, 1.5),  # midpoint of the 1..2 ramp
        "comfortable": (1.5, np.inf),
    }


def test_crisp_intervals_partition_the_line():
    for words in crisp_intervals(VOCAB, CONFIG).values():
        bounds = sorted(words.values())
        assert bounds[0][0] == -np.inf and bounds[-1][1] == np.inf
        assert all(a[1] == b[0] for a, b in zip(bounds, bounds[1:], strict=False))


def test_crisp_rule_boundaries_are_half_open():
    values = delays((1, 2.999), (1, 3.0), (1, 3.999), (1, 4.0))
    on_time = check(claim("few", f"{D}:on_time"), values, VOCAB, CONFIG)
    assert on_time.p_crisp == pytest.approx(0.25)
    late = check(claim("few", f"{D}:late"), values, VOCAB, CONFIG)
    assert late.p_crisp == pytest.approx(0.25)


@pytest.mark.parametrize(
    "q,p,expected",
    [
        ("most", 0.5, False), ("most", 0.5001, True), ("few", 0.25, False),
        ("few", 0.2499, True), ("about_half", 0.4, True), ("about_half", 0.6, True),
        ("about_half", 0.39, False), ("about_half", 0.61, False),
        ("almost_all", 0.99, None),  # extended words: no crisp definition
    ],
)  # fmt: skip
def test_crisp_quantifiers(q, p, expected):
    assert crisp_quantifier(q, p, CONFIG) is expected


def test_crisp_thresholds_come_from_config():
    cfg = {"crisp_baseline": {"punctual_threshold_minutes": 5, "most_threshold": 0.6}}
    assert crisp_intervals(VOCAB, cfg)[D]["on_time"] == (-np.inf, 5.0)
    assert crisp_quantifier("most", 0.55, cfg) is False
    assert crisp_quantifier("few", 0.2, cfg) is True  # default few threshold
    assert CRISP_DEFAULTS["few_threshold"] == 0.25 and CRISP_DEFAULTS["about_half_tolerance"] == 0.1


# --------------------------------------------------------------------- restrictions


def test_restriction_time_band_and_weekday_group():
    values = {
        D: np.array([6.0, 6.0, 0.0, 0.0, 6.0, 0.0]),
        "time_band": np.array(["morning_peak"] * 4 + ["midday"] * 2),
        "weekday": np.array([0, 0, 0, 2, 0, 5]),
    }
    r = check(claim("most", f"{D}:late", "time_band=morning_peak&weekday_group=monday"),
              values, VOCAB, CONFIG)  # fmt: skip
    assert r.n == 3 and r.p_crisp == pytest.approx(2 / 3) and r.crisp is True
    r = check(claim("few", f"{D}:late", "weekday_group=weekend"), values, VOCAB, CONFIG)
    assert r.n == 1 and r.p_crisp == 0.0 and r.crisp is True
    r = check(claim("most", f"{D}:late", "weekday_group=weekday"), values, VOCAB, CONFIG)
    assert r.n == 5  # Mon-Fri


def test_weekday_group_strings_accepted():
    values = {
        D: np.array([6.0, 0.0, 6.0]),
        "weekday_group": np.array(["friday", "friday", "monday"]),
    }
    r = check(claim("about_half", f"{D}:late", "weekday_group=friday"), values, VOCAB, CONFIG)
    assert r.n == 2 and r.p_crisp == pytest.approx(0.5)


def test_attribute_scoped_restriction_columns():
    values = {
        D: np.array([6.0, 0.0]),
        C: np.array([-1.0, -1.0, 3.0]),
        f"{C}.time_band": np.array(["midday", "midday", "night"]),
        "time_band": np.array(["midday", "night"]),
    }
    r = check(claim("most", f"{C}:missed", "time_band=midday"), values, VOCAB, CONFIG)
    assert (r.n, r.crisp) == (2, True)


# --------------------------------------------------------------------- n/a and missing


@pytest.mark.parametrize(
    "c,reason",
    [
        (claim(None, f"{D}:late", status="unverifiable"), "status"),
        (claim("most", f"{D}:late", status="unverifiable_causal"), "status"),
        (claim("most", f"{D}:late", status="inconsistent"), "status"),
        (claim("many", f"{D}:late"), "quantifier"),
        (claim("most", f"{D}:crowded"), "summarizer"),
        (claim("most", f"{C}:missed"), "values"),  # no connection data in segment
        (claim("most", f"{D}:late", "time_band=night"), "empty"),
        (claim("most", f"{D}:late", "canton=BE"), "restriction"),
    ],
)
def test_not_checkable_is_n_a(c, reason):
    values = delays((5, 6.0)) | {"time_band": np.array(["midday"] * 5)}
    r = check(c, values, VOCAB, CONFIG)
    assert (r.crisp, r.fuzzy, r.fuzzy_true, r.disagreement) == (None, None, None, "n/a")
    assert reason in (r.reason or "")
    assert isinstance(r, CheckResult) and r.claim == c


def test_extended_quantifier_fuzzy_only():
    r = check(claim("almost_all", f"{D}:on_time"), delays((100, 0.0)), VOCAB, CONFIG)
    assert r.crisp is None and r.fuzzy == pytest.approx(1.0) and r.disagreement == "n/a"


def test_nan_rows_dropped_by_both_checkers():
    values = {D: np.array([6.0, 6.0, 0.0, np.nan, np.nan])}
    r = check(claim("most", f"{D}:late"), values, VOCAB, CONFIG)
    assert r.n == 3 and r.p_crisp == pytest.approx(2 / 3) and r.p_fuzzy == pytest.approx(2 / 3)


def test_length_mismatch_raises():
    values = {D: np.array([1.0, 2.0]), "time_band": np.array(["midday"])}
    with pytest.raises(ValueError):
        check(claim("most", f"{D}:late", "time_band=midday"), values, VOCAB, CONFIG)


# --------------------------------------------------------------------- review #43


FIXTURE = ROOT / "tests" / "fixtures" / "ist_sample"


def _borderline_delays() -> np.ndarray:
    """Arrival delays (min) of the UC-004 borderline segment, read from the fixture CSVs:
    Zürich HB, line IC1, REAL arrivals (no pass-through, extra or cancelled trips)."""
    import csv
    from datetime import datetime

    out = []
    for path in sorted(FIXTURE.glob("*_IstDaten.csv")):
        with path.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh, delimiter=";"):
                if (r["HALTESTELLEN_NAME"], r["LINIEN_TEXT"]) != ("Zürich HB", "IC1"):
                    continue
                if "true" in (r["DURCHFAHRT_TF"], r["ZUSATZFAHRT_TF"], r["FAELLT_AUS_TF"]):
                    continue
                if r["AN_PROGNOSE_STATUS"] != "REAL" or not r["ANKUNFTSZEIT"]:
                    continue
                planned = datetime.strptime(r["ANKUNFTSZEIT"], "%d.%m.%Y %H:%M")
                actual = datetime.strptime(r["AN_PROGNOSE"], "%d.%m.%Y %H:%M:%S")
                out.append((actual - planned).total_seconds() / 60.0)
    return np.array(out)


def test_uc004_borderline_fixture():
    """The ticket's borderline fixture: Zürich HB IC1, 13 x 3 min and 12 x 0 min."""
    import json

    truth = json.loads((FIXTURE / "ground_truth.json").read_text(encoding="utf-8"))
    seg = next(s for s in truth["segments"] if (s["hub"], s["line"]) == ("Zürich HB", "IC1"))
    x = _borderline_delays()
    assert int((x < 3).sum()) == seg["delay_counts"]["under_3_min"] == 12
    assert int((x >= 3).sum()) == seg["delay_counts"]["at_least_3_min"] == 13
    values = {D: x}

    late = check(claim("most", f"{D}:late"), values, VOCAB, CONFIG)
    assert (late.crisp, late.fuzzy, late.disagreement) == (False, 0.0, "none")
    assert late.p_crisp == 0.0 and late.n == 25  # crisp late = [4, 9): no 3-min row

    slightly = check(claim("most", f"{D}:slightly_late"), values, VOCAB, CONFIG)
    assert slightly.crisp is True and slightly.p_crisp == pytest.approx(0.52)
    assert slightly.fuzzy == pytest.approx((0.52 - 0.5) / 0.35)  # 0.057
    assert slightly.disagreement == "crisp_true_fuzzy_false"


def test_cancelled_connections_encoded_minus_inf_count_as_missed():
    cancelled = np.array([3.0, 3.0, 3.0, -1.0, -np.inf, -np.inf])
    r = check(claim("about_half", f"{C}:missed"), {C: cancelled}, VOCAB, CONFIG)
    assert r.n == 6  # not dropped
    assert r.p_crisp == pytest.approx(0.5) and r.p_fuzzy == pytest.approx(0.5)
    assert r.crisp is True and r.fuzzy == pytest.approx(1.0)
    for word in ("tight", "comfortable"):
        other = check(claim("few", f"{C}:{word}"), {C: cancelled}, VOCAB, CONFIG)
        assert other.n == 6 and other.p_crisp == pytest.approx(0.0 if word == "tight" else 0.5)
    # NaN = unknown: dropped, which would understate the passenger's missed share
    unknown = np.array([3.0, 3.0, 3.0, -1.0, np.nan, np.nan])
    r = check(claim("few", f"{C}:missed"), {C: unknown}, VOCAB, CONFIG)
    assert r.n == 4 and r.p_fuzzy == pytest.approx(0.25)


def test_decision_d023_recorded():
    rows = [ln for ln in (ROOT / "docs" / "decisions.md").read_text().splitlines()
            if ln.startswith("| D-023 ")]  # fmt: skip
    assert len(rows) == 1
    assert rows[0].split("|")[3].strip() in {"proposed", "accepted"}
    sec6 = (ROOT / "docs" / "methods.md").read_text().split("## 6. Claim checkers")[1]
    assert "SRQ2" in sec6 and "−∞" in sec6 and "D-023" in sec6
