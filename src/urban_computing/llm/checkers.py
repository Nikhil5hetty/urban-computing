"""Crisp and fuzzy claim checkers (UC-042). Stub."""

from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel

from urban_computing.fuzzy.vocabulary import Vocabulary
from urban_computing.llm.parser import Claim

Disagreement = Literal["none", "crisp_true_fuzzy_false", "crisp_false_fuzzy_true", "n/a"]


class CheckResult(BaseModel):
    claim: Claim
    crisp: bool | None
    fuzzy: float | None
    fuzzy_true: bool | None  # fuzzy >= 0.5
    disagreement: Disagreement


def check(
    claim: Claim, values: dict[str, np.ndarray], vocab: Vocabulary, config: dict
) -> CheckResult:
    """Score one claim against the segment's raw values with both checkers."""
    raise NotImplementedError("UC-042")
