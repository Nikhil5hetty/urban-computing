"""Crisp official-view baseline (UC-032). Stub."""

from __future__ import annotations

import pandas as pd

from urban_computing.assistant.contract import Answer, Question


def crisp_answer(question: Question, arrivals: pd.DataFrame, config: dict) -> Answer:
    """SBB 3-minute rule on the arriving line at the hub; ignores margin_min."""
    raise NotImplementedError("UC-032")
