"""Crisp official-view baseline (UC-032). Rule: docs/methods.md §5 (crisp baseline).

The answer an official punctuality statistic gives for the same Question: the SBB rule
(< 3 min late = punctual, D-007) applied to the arriving line's REAL arrivals at the hub in
the question's time band and weekday group. The passenger's margin is ignored by design.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd

from urban_computing.assistant.contract import Answer, Decision, Provenance, Question

_WEEKDAY_GROUPS: dict[str, tuple[int, ...]] = {
    "weekday": (0, 1, 2, 3, 4),
    "monday": (0,),
    "friday": (4,),
    "weekend": (5, 6),
    "all": (0, 1, 2, 3, 4, 5, 6),
}
_WEEKDAY_TEXT: dict[str, str] = {
    "weekday": "on weekdays",
    "monday": "on Mondays",
    "friday": "on Fridays",
    "weekend": "at weekends",
    "all": "on all days",
}


class NoArrivalsError(ValueError):
    """No measured arrival of the question's line at the hub in its time band / weekday group."""


def _baseline(config: dict) -> dict[str, Any]:
    cb = config.get("crisp_baseline") or {}
    t = cb.get("decision_thresholds") or {}
    return {
        "punctual": float(cb.get("punctual_threshold_minutes", 3)),
        "most": float(cb.get("most_threshold", 0.5)),
        "at_risk": float(t["at_risk"]),
        "risky": float(t["risky"]),
    }


def crisp_decision(p_late: float, config: dict) -> Decision:
    """Decision word for the crisp late share p in [0, 1] (config `crisp_baseline`).

    safe if p < at_risk, at_risk if at_risk <= p < risky, risky if p >= risky
    (0.075 / 0.25: crossovers of the fuzzy decision words, methods §5).
    """
    b = _baseline(config)
    if p_late >= b["risky"]:
        return "risky"
    return "at_risk" if p_late >= b["at_risk"] else "safe"


def _segment(question: Question, arrivals: pd.DataFrame) -> pd.DataFrame:
    a = arrivals
    sel = (a["stop_name"] == question.hub) & (a["time_band"] == question.time_band)
    sel &= a["weekday"].isin(_WEEKDAY_GROUPS[question.weekday_group])
    if question.arr_line:
        sel &= a["line"] == question.arr_line
    else:
        sel &= a["product"] == question.arr_product
    seg = a.loc[sel]
    return seg.loc[~seg["cancelled"].astype(bool) & seg["delay_min"].notna()]


def _config_hash(config: dict) -> str:
    blob = json.dumps(config, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def crisp_answer(question: Question, arrivals: pd.DataFrame, config: dict) -> Answer:
    """SBB 3-minute rule on the arriving line at the hub; ignores margin_min.

    Inputs: the Question, an ARRIVALS frame (schemas.ARRIVALS; REAL arrivals), the study
    config. Rows: `stop_name` = hub, `line` = arr_line (else `product` = arr_product),
    the question's time band and weekday group; cancelled arrivals and rows without a
    measured delay are not counted. p_late = share with delay >= punctual threshold (min).
    Returns an Answer with `decision` = `crisp_decision` and two crisp sentences
    ("most" = more than half, D-012); no fuzzy explanations. Raises NoArrivalsError if no
    row is left.
    """
    seg = _segment(question, arrivals)
    what = question.arr_line or question.arr_product
    if seg.empty:
        raise NoArrivalsError(
            f"no measured {what} arrivals at {question.hub} ({question.time_band}, "
            f"{question.weekday_group})"
        )
    b = _baseline(config)
    n = int(len(seg))
    n_late = int((seg["delay_min"] >= b["punctual"]).sum())
    decision = crisp_decision(n_late / n, config)

    where = (
        f"{what} arrivals at {question.hub} in the {question.time_band.replace('_', ' ')} "
        f"{_WEEKDAY_TEXT[question.weekday_group]}"
    )
    q = "Most" if (n - n_late) / n > b["most"] else "At most half of"
    minutes = f"{b['punctual']:g}"
    sentences = [
        f"{q} {where} are punctual (less than {minutes} minutes late).",
        f"{n_late} of {n} arrivals were {minutes} or more minutes late.",
    ]
    period = config["data"]["period"]
    return Answer(
        question=question,
        decision=decision,
        crisp_decision=decision,
        crisp_sentences=sentences,
        provenance=Provenance(
            period=f"{period['start']}..{period['end']}", config_hash=_config_hash(config)
        ),
    )
