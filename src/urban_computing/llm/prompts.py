"""Deterministic prompt templates for SRQ3 (UC-040)."""

from __future__ import annotations

import json

from urban_computing.assistant.contract import Answer, Question

STUDY_CONDITIONS = ("stats_only", "fuzzy_grounded")
CONDITIONS = (*STUDY_CONDITIONS, "query_tool")

_QUESTION = """\
You are writing for a passenger using Swiss public transport.
Question: How reliable is my transfer at {hub} from {route} with {margin:g} minutes to change?
Time band: {band}. Days: {days}.
"""
_DAYS = {
    "monday": "Mondays",
    "friday": "Fridays",
    "weekday": "weekdays",
    "weekend": "weekends",
    "all": "all days",
}
_STATS = "Segment statistics (delays in minutes, shares from 0 to 1):\n{stats}"
_GROUNDED = "Assistant decision: {decision}.\nSupported explanations (truth from 0 to 1):"
_INSTRUCTIONS = """\
Write a citizen answer of at most three sentences.
Use only these quantifiers: few, about half, most.
Use only these outcome words: on time, slightly late, late, very late, missed, tight, comfortable.
Use only claims supported by the evidence and keep their scope.
If the evidence cannot support a claim in this vocabulary, leave it out.
Return one JSON object followed by the same citizen answer as plain text:
{"claims": [{"quantifier": "...", "summarizer": "...", "restriction": null}], "text": "..."}
Use null for the question's own segment, or name the narrower restriction in words.
Include one entry per quantified claim in the text. Use an empty claims list if there are none."""


def render_prompt(
    condition: str, question: Question, stats: dict | None = None, answer: Answer | None = None
) -> str:
    """Render one prompt using segment stats (minutes and shares) or a fuzzy Answer."""
    route = question.arr_line or question.arr_product
    departure = question.dep_line or question.dep_product
    if departure:
        route = f"{route} to {departure}"
    context = _QUESTION.format(
        hub=question.hub,
        route=route,
        margin=question.margin_min,
        band=question.time_band.replace("_", " "),
        days=_DAYS[question.weekday_group],
    )
    if condition == "stats_only":
        if stats is None:
            raise ValueError("stats_only requires segment statistics")
        evidence = _STATS.format(stats=json.dumps(stats, sort_keys=True, allow_nan=False))
    elif condition == "fuzzy_grounded":
        if answer is None:
            raise ValueError("fuzzy_grounded requires an assistant Answer")
        if answer.question != question:
            raise ValueError("fuzzy_grounded Answer must match the question")
        lines = [_GROUNDED.format(decision=answer.decision.replace("_", " "))]
        lines.extend(f"- {e.sentence} (truth {e.truth}, n={e.n})" for e in answer.explanations)
        if answer.provenance.fallback:
            lines.append(
                "The assistant used arrival delays because too few matching connections "
                "were available."
            )
        evidence = "\n".join(lines)
    else:
        raise ValueError(f"Unsupported prompt condition: {condition!r}")
    return f"{context}{evidence}\n\n{_INSTRUCTIONS}"
