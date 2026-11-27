"""UC-032: crisp official-view baseline (SBB 3-minute rule on the arriving line)."""

from __future__ import annotations

import copy
from pathlib import Path

import pandas as pd
import pytest
import yaml

from tests import factories
from urban_computing.assistant.contract import Answer
from urban_computing.assistant.crisp import NoArrivalsError, crisp_answer, crisp_decision

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "config" / "study.yaml").read_text())
Q = factories.sample_question  # Olten, IC1 -> IR16, morning_peak, monday, margin 4


def late_share(n_late: int, n: int, late: float = 5.0, on_time: float = 0.0) -> pd.DataFrame:
    """n arrivals of IC1 at Olten (Monday morning peak), n_late of them >= 3 min late."""
    return factories.arrivals([late] * n_late + [on_time] * (n - n_late))


# --------------------------------------------------------------------- acceptance


def test_returns_answer_with_crisp_decision_and_sentences():
    a = crisp_answer(Q(), late_share(10, 200), CONFIG)
    assert isinstance(a, Answer)
    assert a.crisp_decision == a.decision == "safe"  # 10 / 200 = 0.05 < 0.075
    assert a.crisp_sentences and a.explanations == [] and a.p_miss is None
    assert a.question == Q()
    assert a.provenance.period == "2026-10-01..2026-10-28" and a.provenance.fallback is False
    assert a.provenance.config_hash
    assert "Official punctuality view: safe." in a.to_text()


@pytest.mark.parametrize("margin", [0.5, 2, 3, 4, 6, 10, 30])
def test_independent_of_margin(margin):
    data = late_share(30, 200)
    base = crisp_answer(Q(), data, CONFIG)
    other = crisp_answer(Q(margin_min=margin), data, CONFIG)
    assert other.model_dump(exclude={"question"}) == base.model_dump(exclude={"question"})


@pytest.mark.parametrize(
    "n_late,decision",
    [(0, "safe"), (14, "safe"), (15, "at_risk"), (49, "at_risk"), (50, "risky"), (200, "risky")],
)
def test_thresholds_from_config(n_late, decision):
    # 200 arrivals: 15 -> p 0.075 (at_risk boundary), 50 -> p 0.25 (risky boundary)
    assert crisp_answer(Q(), late_share(n_late, 200), CONFIG).crisp_decision == decision
    assert crisp_decision(n_late / 200, CONFIG) == decision


def test_thresholds_are_read_from_config():
    cfg = copy.deepcopy(CONFIG)
    cfg["crisp_baseline"]["decision_thresholds"] = {"at_risk": 0.01, "risky": 0.04}
    assert crisp_answer(Q(), late_share(10, 200), cfg).crisp_decision == "risky"
    cfg["crisp_baseline"]["punctual_threshold_minutes"] = 6  # 5-min delays now punctual
    assert crisp_answer(Q(), late_share(10, 200), cfg).crisp_decision == "safe"


def test_config_and_methods_mirror_the_thresholds():
    t = CONFIG["crisp_baseline"]["decision_thresholds"]
    assert (t["at_risk"], t["risky"]) == (0.075, 0.25)
    methods = (ROOT / "docs" / "methods.md").read_text()
    sec5 = methods[methods.index("## 5.") : methods.index("## 6.")]
    for token in ("0.075", "0.25", "≥ 3 min", "D-007", "D-012", "UC-032", "margin"):
        assert token in sec5, token


# --------------------------------------------------------------------- the SBB rule


def test_three_minutes_late_is_not_punctual():
    data = factories.arrivals([3.0] * 15 + [2.99] * 185)
    a = crisp_answer(Q(), data, CONFIG)
    assert a.crisp_decision == "at_risk"  # exactly 15 of 200 are >= 3 min


def test_sentences_use_crisp_most_and_state_counts():
    a = crisp_answer(Q(), late_share(10, 200), CONFIG)
    assert a.crisp_sentences[0] == (
        "Most IC1 arrivals at Olten in the morning peak on Mondays are punctual "
        "(less than 3 minutes late)."
    )
    assert a.crisp_sentences[1] == "10 of 200 arrivals were 3 or more minutes late."
    half = crisp_answer(Q(), late_share(100, 200), CONFIG)  # 0.5 is not "more than half"
    assert half.crisp_sentences[0].startswith("At most half of IC1 arrivals")
    assert crisp_answer(Q(), late_share(99, 200), CONFIG).crisp_sentences[0].startswith("Most")


# --------------------------------------------------------------------- segment selection


def test_selects_only_the_questions_segment():
    seg = late_share(10, 200)
    noise = pd.concat(
        [
            factories.arrivals([20.0] * 50, stop_name="Bern"),
            factories.arrivals([20.0] * 50, line="IC5"),
            factories.arrivals([20.0] * 50, time_band="midday"),
            factories.arrivals([20.0] * 50, operating_day=factories.DEFAULT_DAY.replace(day=7)),
        ],
        ignore_index=True,
    )  # Bern / other line / other band / a Wednesday: all very late
    a = crisp_answer(Q(), pd.concat([seg, noise], ignore_index=True), CONFIG)
    assert a.crisp_decision == "safe" and "10 of 200" in a.crisp_sentences[1]


def test_product_when_no_line_and_weekday_groups():
    data = pd.concat(
        [late_share(0, 10), factories.arrivals([9.0] * 10, line="IC8")], ignore_index=True
    )
    by_product = crisp_answer(Q(arr_line=None, arr_product="IC"), data, CONFIG)
    assert by_product.crisp_decision == "risky"  # both IC lines: 10 of 20 late
    assert "IC arrivals" in by_product.crisp_sentences[0]
    weekday = crisp_answer(Q(weekday_group="weekday"), late_share(0, 10), CONFIG)
    assert weekday.crisp_decision == "safe"
    with pytest.raises(NoArrivalsError):
        crisp_answer(Q(weekday_group="weekend"), late_share(0, 10), CONFIG)


def test_cancelled_and_unmeasured_arrivals_are_not_counted():
    data = factories.arrivals([5.0] * 10 + [0.0] * 190 + [None] * 50)
    a = crisp_answer(Q(), data, CONFIG)
    assert "10 of 200" in a.crisp_sentences[1]  # 50 cancellations excluded


def test_no_arrivals_raises():
    with pytest.raises(NoArrivalsError, match="Basel|IC1"):
        crisp_answer(Q(), factories.arrivals([None] * 5), CONFIG)
    assert issubclass(NoArrivalsError, ValueError)


# --------------------------------------------------------------------- review #51: stop ids

from urban_computing.assistant.crisp import NAME_FALLBACK_NOTE, hub_stop_keys  # noqa: E402

ID_CONFIG = copy.deepcopy(CONFIG)
ID_CONFIG["connections"]["hub_stop_ids"] = {"Olten": ["8500218", "ch:1:sloid:218"]}


def test_hub_matched_by_stop_id_not_name():
    hub = late_share(10, 200)  # stop_id 8500218, stop_name "Olten"
    same_name_other_id = factories.arrivals([20.0] * 100, stop_id="8599999")  # also "Olten"
    a = crisp_answer(Q(), pd.concat([hub, same_name_other_id], ignore_index=True), ID_CONFIG)
    assert "10 of 200" in a.crisp_sentences[1] and a.crisp_decision == "safe"
    assert NAME_FALLBACK_NOTE not in a.crisp_sentences


@pytest.mark.parametrize(
    "stop_id,stop_name",
    [
        ("8500218", ""),  # blank operator-supplied name
        ("850021800", "Olten"),  # nine-digit BPUIC -> first seven digits
        ("ch:1:sloid:218", "Olten"),  # stop SLOID
        ("ch:1:sloid:218:3:5", "Olten Gleis 5"),  # child SLOID -> stop SLOID
        (" 8500218 ", "OLTEN"),  # whitespace; name irrelevant
    ],
)
def test_hub_ids_include_bpuic_and_child_sloid_whatever_the_name(stop_id, stop_name):
    data = factories.arrivals([5.0] * 3 + [0.0] * 7, stop_id=stop_id, stop_name=stop_name)
    a = crisp_answer(Q(), data, ID_CONFIG)
    assert "3 of 10" in a.crisp_sentences[1]


def test_name_fallback_only_without_id_mapping_and_is_stated():
    a = crisp_answer(Q(), late_share(10, 200), CONFIG)  # study.yaml has no hub_stop_ids
    assert a.crisp_sentences[-1] == NAME_FALLBACK_NOTE
    assert NAME_FALLBACK_NOTE in a.to_text()
    assert hub_stop_keys("Olten", CONFIG) is None
    assert hub_stop_keys("Olten", ID_CONFIG) == {"8500218", "ch:1:sloid:218"}


def test_mapping_without_the_hub_raises():
    cfg = copy.deepcopy(ID_CONFIG)
    cfg["connections"]["hub_stop_ids"] = {"Bern": ["8507000"]}
    with pytest.raises(ValueError, match="Olten"):
        crisp_answer(Q(), late_share(1, 10), cfg)


def test_stop_key_regex_identical_to_uc014_connections():
    """crisp uses data.arrivals._stop_key; UC-014 uses the SQL in data.connections._stop_key."""
    import inspect
    import re

    from urban_computing.data import arrivals as arr
    from urban_computing.data import connections as con

    def pattern(src: str) -> str:
        return re.search(r"\^\(\[0-9\]\{7\}\).*?\$'?\"?,", src).group(0).rstrip("',\"")

    assert pattern(inspect.getsource(arr._stop_key)) == pattern(inspect.getsource(con._stop_key))
