"""Question/Answer contract (fields are the frozen INTERFACE; UC-030 adds validators,
`to_text()` and tests). Every component exchanges these objects."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Decision = Literal["safe", "at_risk", "risky"]
WeekdayGroup = Literal["weekday", "monday", "friday", "weekend", "all"]


class Question(BaseModel):
    hub: str
    arr_line: str | None = None
    arr_product: str | None = None
    dep_line: str | None = None
    dep_product: str | None = None
    time_band: str
    weekday_group: WeekdayGroup = "weekday"
    margin_min: float = Field(description="passenger's planned transfer time, minutes")
    question_id: str | None = None


class Explanation(BaseModel):
    sentence: str
    quantifier: str
    summarizer: str
    restriction: str | None = None
    truth: float
    coverage: float | None = None
    quality: float | None = None
    n: int


class Provenance(BaseModel):
    period: str  # e.g. "2026-10-01..2026-10-28"
    config_hash: str
    git_sha: str | None = None
    fallback: bool = False  # True if the engine used arrivals instead of connections


class Answer(BaseModel):
    question: Question
    decision: Decision
    p_miss: float | None = None  # fuzzy proportion behind the decision (UC-031)
    explanations: list[Explanation] = Field(default_factory=list)
    crisp_decision: Decision | None = None
    crisp_sentences: list[str] = Field(default_factory=list)
    provenance: Provenance

    def to_text(self) -> str:
        """Citizen-facing paragraph rendered only from fields (UC-030)."""
        raise NotImplementedError("UC-030")
