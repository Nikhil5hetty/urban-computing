"""Perception-aware connection-risk decision with faithful explanation (UC-031). Stub."""

from __future__ import annotations

import pandas as pd

from urban_computing.assistant.contract import Answer, Question
from urban_computing.fuzzy.vocabulary import Vocabulary


def answer(
    question: Question,
    connections: pd.DataFrame,
    arrivals: pd.DataFrame,
    vocab: Vocabulary,
    config: dict,
) -> Answer:
    """Decision word + explanation from the same truth computation (invariant I4)."""
    raise NotImplementedError("UC-031")


def verify_answer(
    ans: Answer,
    connections: pd.DataFrame,
    arrivals: pd.DataFrame,
    vocab: Vocabulary,
    config: dict,
    tol: float = 1e-9,
) -> bool:
    """Recompute every explanation's truth from the data; True iff all match (I4)."""
    raise NotImplementedError("UC-031")
