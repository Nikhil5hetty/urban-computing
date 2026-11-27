"""Pure render helpers for the prototype (UC-060).

Every text and number the app shows is derived here from an `Answer` (or from checked LLM
claims), so it can be tested without a UI. No I/O, no Streamlit import.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from typing import Any

from urban_computing.assistant.contract import Answer

GREEN, AMBER = 0.6, 0.3  # truth badge thresholds (ticket UC-060)
DECISION_LABEL = {"safe": "Safe", "at_risk": "At risk", "risky": "Risky"}
DECISION_COLOR = {"safe": "green", "at_risk": "orange", "risky": "red"}
SOURCE = "opentransportdata.swiss (Ist-Daten, {month})"
COUNT_QUANTIFIER = "count"  # measured-share sentence of the engine (UC-031)
OWN_RESTRICTIONS = ("own_connections", "own_arrivals")  # engine's own-segment markers
BADGE_HEX = {"green": "#1a7f37", "amber": "#b26a00", "red": "#c62828", "gray": "#6e7781"}


def truth_badge(truth: float) -> str:
    """'green' if truth >= 0.6, 'amber' if 0.3 <= truth < 0.6, else 'red'."""
    if truth >= GREEN:
        return "green"
    if truth >= AMBER:
        return "amber"
    return "red"


def truth_bar_html(fraction: float, badge: str) -> str:
    """A truth bar coloured by its badge (green / amber / red), not by the app theme, so a
    fully true sentence never looks like an alarm (PM review of #58). Pure HTML string."""
    pct = round(100 * max(0.0, min(1.0, fraction)), 1)
    color = BADGE_HEX[badge]
    return (
        "<div style='background:#e6e6e6;border-radius:4px;height:10px;width:100%'>"
        f"<div style='background:{color};width:{pct}%;height:10px;border-radius:4px'></div></div>"
    )


def _month(period: str) -> str:
    """'2026-10-01..2026-10-28' -> 'Oct 2026' (both ends in one month), else the period."""
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})", period.strip())
    if not m:
        return period
    start, end = date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
    if (start.year, start.month) == (end.year, end.month):
        return start.strftime("%b %Y")
    return f"{start.strftime('%b %Y')} to {end.strftime('%b %Y')}"


def footer_text(ans: Answer) -> str:
    """'Data: opentransportdata.swiss (Ist-Daten, Oct 2026)' from the Answer's data period."""
    return "Data: " + SOURCE.format(month=_month(ans.provenance.period))


def _question_line(ans: Answer) -> str:
    q = ans.question
    route = q.arr_line or q.arr_product
    dep = q.dep_line or q.dep_product
    if dep:
        route = f"{route} → {dep}"
    days = {"weekday": "weekdays", "monday": "Mondays", "friday": "Fridays",
            "weekend": "weekends", "all": "all days"}[q.weekday_group]  # fmt: skip
    return (
        f"{q.hub} · {route} · {q.time_band.replace('_', ' ')} · {days} · "
        f"{q.margin_min:g} min to change"
    )


def answer_view_model(ans: Answer) -> dict:
    """Everything the UI displays, derived only from the Answer.

    Keys: question (one line), decision {word, label, color}, explanations [{sentence,
    truth (2 decimals) or None for a measured-share sentence, truth_value, badge, bar
    (0..1), bar_html (bar in the badge colour) or None, coverage text or None, n, n_text}],
    own_sentences (the sentences on the passenger's own connections / arrivals, for the
    side-by-side Official view), official {decision, label, color, sentences} or None,
    fallback_note or None, period, footer.
    """
    explanations = []
    for e in ans.explanations:
        is_count = e.quantifier == COUNT_QUANTIFIER
        explanations.append(
            {
                "sentence": e.sentence,
                "truth": None if is_count else f"{e.truth:.2f}",
                "truth_value": None if is_count else e.truth,
                "badge": None if is_count else truth_badge(e.truth),
                "bar": None if is_count else max(0.0, min(1.0, e.truth)),
                "bar_html": None if is_count else truth_bar_html(e.truth, truth_badge(e.truth)),
                "coverage": None if e.coverage is None or is_count else f"{e.coverage:.2f}",
                "n": e.n,
                "n_text": f"based on {e.n} observations",
            }
        )
    official = None
    if ans.crisp_decision is not None or ans.crisp_sentences:
        official = {
            "decision": ans.crisp_decision,
            "label": DECISION_LABEL.get(ans.crisp_decision or "", "No verdict"),
            "color": DECISION_COLOR.get(ans.crisp_decision or "", "gray"),
            "sentences": list(ans.crisp_sentences),
        }
    return {
        "question": _question_line(ans),
        "decision": {
            "word": ans.decision,
            "label": DECISION_LABEL[ans.decision],
            "color": DECISION_COLOR[ans.decision],
        },
        "explanations": explanations,
        "own_sentences": [
            e.sentence for e in ans.explanations if e.restriction in OWN_RESTRICTIONS
        ],
        "official": official,
        "fallback_note": (
            "Based on arrival delays only, because too few matching connections were found."
            if ans.provenance.fallback
            else None
        ),
        "period": ans.provenance.period,
        "footer": footer_text(ans),
    }


def chatbot_view_model(text: str, results: Sequence[Any]) -> dict:
    """Cached LLM answer with one badge per claim (SRQ3 story; no LLM call).

    `results` are `llm.checkers.CheckResult`s. Per claim: the claim text, the fuzzy truth
    (2 decimals) and its badge, or "not checkable" with the reason (status not ok, word not
    in the vocabulary, no data).
    """
    claims = []
    for r in results:
        claim = r.claim
        label = claim.text or " ".join(x for x in (claim.quantifier, claim.summarizer) if x)
        if r.fuzzy is None:
            claims.append({"text": label, "truth": None, "badge": "gray",
                           "note": f"not checkable ({r.reason or claim.status})"})  # fmt: skip
        else:
            claims.append({"text": label, "truth": f"{r.fuzzy:.2f}", "badge": truth_badge(r.fuzzy),
                           "note": None})  # fmt: skip
    return {"text": text, "claims": claims}
