"""UC-030: Question/Answer contract validators, JSON round trip and to_text()."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from tests import factories
from urban_computing.assistant.contract import Answer, Explanation, Provenance, Question

# --------------------------------------------------------------------- JSON round trip


def test_question_json_round_trip_is_lossless():
    q = factories.sample_question(dep_product="IR", arr_product="IC")
    assert Question.model_validate_json(q.model_dump_json()) == q


def test_answer_json_round_trip_is_lossless():
    a = factories.sample_answer(
        provenance=Provenance(
            period="2026-10-01..2026-10-28", config_hash="abc", git_sha="1234567", fallback=True
        )
    )
    b = Answer.model_validate_json(a.model_dump_json())
    assert b == a
    assert b.model_dump_json() == a.model_dump_json()


# --------------------------------------------------------------------- validators


@pytest.mark.parametrize("margin", [0, -1, -0.5, float("nan"), float("inf")])
def test_margin_must_be_positive_and_finite(margin):
    with pytest.raises(ValidationError, match="margin_min"):
        factories.sample_question(margin_min=margin)


def test_unknown_hub_rejected():
    with pytest.raises(ValidationError, match="hub"):
        factories.sample_question(hub="Basel SBB")


def test_unknown_time_band_rejected():
    with pytest.raises(ValidationError, match="time_band"):
        factories.sample_question(time_band="lunch")


def test_needs_arr_line_or_arr_product():
    with pytest.raises(ValidationError, match="arr_line or arr_product"):
        factories.sample_question(arr_line=None, arr_product=None)
    assert factories.sample_question(arr_line=None, arr_product="IC").arr_product == "IC"


@pytest.mark.parametrize("hub", ["Zürich HB", "Bern", "Olten"])
@pytest.mark.parametrize(
    "band", ["early", "morning_peak", "midday", "evening_peak", "evening", "night"]
)
def test_all_config_hubs_and_time_bands_accepted(hub, band):
    assert factories.sample_question(hub=hub, time_band=band).hub == hub


def test_validation_context_overrides_study_config():
    cfg = {"connections": {"hubs": ["Basel SBB"]}, "time_bands": {"lunch": ["11:00", "14:00"]}}
    data = factories.sample_question().model_dump() | {"hub": "Basel SBB", "time_band": "lunch"}
    q = Question.model_validate(data, context={"study_config": cfg})
    assert (q.hub, q.time_band) == ("Basel SBB", "lunch")
    with pytest.raises(ValidationError):
        Question.model_validate(data)  # default config: Basel SBB is not a study hub


# --------------------------------------------------------------------- to_text snapshots

SNAPSHOT_DEFAULT = (
    "Your connection at Olten from IC1 to IR16 in the morning peak on Mondays, "
    "with 4 minutes to change: at risk.\n"
    "Why: Few of your connections at Olten are missed. (truth 0.74, based on 38 observations)\n"
    "Official punctuality view: safe. Most IC1 arrivals at Olten are punctual.\n"
    "Data period: 2026-10-01..2026-10-28."
)


def test_to_text_snapshot_default_answer():
    assert factories.sample_answer().to_text() == SNAPSHOT_DEFAULT


def test_to_text_snapshot_minimal_answer():
    a = Answer(
        question=Question(
            hub="Bern", arr_product="IC", time_band="evening", weekday_group="all", margin_min=2.5
        ),
        decision="safe",
        provenance=Provenance(period="2026-10-01..2026-10-28", config_hash="x"),
    )
    assert a.to_text() == (
        "Your connection at Bern from IC in the evening on all days, "
        "with 2.5 minutes to change: safe.\n"
        "Data period: 2026-10-01..2026-10-28."
    )


def test_to_text_snapshot_fallback_and_several_explanations():
    exp2 = Explanation(
        sentence="About half of IC1 arrivals are slightly late.",
        quantifier="about_half",
        summarizer="arrival_delay_minutes:slightly_late",
        truth=0.51,
        n=120,
    )
    a = factories.sample_answer(
        decision="risky",
        explanations=[*factories.sample_answer().explanations, exp2],
        crisp_decision=None,
        crisp_sentences=[],
        provenance=Provenance(period="2026-10-01..2026-10-28", config_hash="x", fallback=True),
    )
    assert a.to_text() == (
        "Your connection at Olten from IC1 to IR16 in the morning peak on Mondays, "
        "with 4 minutes to change: risky.\n"
        "Why: Few of your connections at Olten are missed. (truth 0.74, based on 38 "
        "observations) About half of IC1 arrivals are slightly late. (truth 0.51, based on "
        "120 observations)\n"
        "Note: this is based on arrival delays only, because no matching connections were "
        "found.\n"
        "Data period: 2026-10-01..2026-10-28."
    )


# --------------------------------------------------------------------- no new facts


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text))


@pytest.mark.parametrize("decision", ["safe", "at_risk", "risky"])
def test_to_text_numbers_all_come_from_fields(decision):
    """Every number in the text appears in the fields' own text or values (no new facts)."""
    a = factories.sample_answer(decision=decision)
    allowed = _numbers(a.model_dump_json()) | {f"{e.truth:.2f}" for e in a.explanations}
    allowed |= {f"{a.question.margin_min:g}"}
    assert _numbers(a.to_text()) <= allowed


def test_to_text_does_not_render_unset_or_internal_fields():
    a = factories.sample_answer()
    text = a.to_text()
    for internal in (a.provenance.config_hash, "p_miss", "0.18", "coverage", "quality",
                     a.question.question_id):  # fmt: skip
        assert internal not in text
    # decision words only from decision / crisp_decision
    assert "risky" not in text
