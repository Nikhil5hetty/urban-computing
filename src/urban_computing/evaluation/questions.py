"""Fixed evaluation question set (UC-033). Stub."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from urban_computing.assistant.contract import Question


def make_questions(connections: pd.DataFrame, config: dict, seed: int) -> list[Question]:
    """Stratified, seeded question set (>= config evaluation.n_questions)."""
    raise NotImplementedError("UC-033")


def write_questions(questions: list[Question], path: Path) -> None:
    """Write eval/questions.jsonl deterministically."""
    raise NotImplementedError("UC-033")
