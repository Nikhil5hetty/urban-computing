"""Question/Answer contract (fields are the frozen INTERFACE; UC-030 adds validators,
`to_text()` and tests). Every component exchanges these objects.

Validation of `Question.hub` / `Question.time_band` uses `config/study.yaml`
(`connections.hubs`, `time_bands`). Pass another study config with
`Question.model_validate(data, context={"study_config": cfg})`.
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

STUDY_CONFIG = Path(__file__).resolve().parents[3] / "config" / "study.yaml"


@lru_cache(maxsize=1)
def _default_study_config() -> dict[str, Any]:
    import yaml

    return yaml.safe_load(STUDY_CONFIG.read_text(encoding="utf-8"))


def _study_config(info: ValidationInfo) -> dict[str, Any]:
    ctx = info.context or {}
    return ctx.get("study_config") or _default_study_config()


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

    @field_validator("margin_min")
    @classmethod
    def _margin_positive(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0:
            raise ValueError("margin_min must be a finite number of minutes > 0")
        return v

    @field_validator("hub")
    @classmethod
    def _known_hub(cls, v: str, info: ValidationInfo) -> str:
        hubs = (_study_config(info).get("connections") or {}).get("hubs") or []
        if v not in hubs:
            raise ValueError(f"hub {v!r} is not a study hub {hubs}")
        return v

    @field_validator("time_band")
    @classmethod
    def _known_time_band(cls, v: str, info: ValidationInfo) -> str:
        bands = list((_study_config(info).get("time_bands") or {}).keys())
        if v not in bands:
            raise ValueError(f"time_band {v!r} is not one of {bands}")
        return v

    @model_validator(mode="after")
    def _needs_arrival(self) -> Question:
        if not self.arr_line and not self.arr_product:
            raise ValueError("give arr_line or arr_product (the arriving train)")
        return self


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
        """Citizen-facing paragraph (English) rendered only from this Answer's fields.

        Lines: the question and decision; "Why:" with each explanation sentence, its truth
        (2 decimals) and n; the crisp (official punctuality) view if present; a note when
        the engine fell back to arrivals; the data period. Adds no fact that is not a field;
        internal fields (p_miss, coverage, quality, hashes, ids) are not rendered.
        """
        q = self.question
        route = q.arr_line or q.arr_product
        dep = q.dep_line or q.dep_product
        if dep:
            route = f"{route} to {dep}"
        lines = [
            f"Your connection at {q.hub} from {route} in the {_words(q.time_band)} "
            f"{_WEEKDAY_TEXT[q.weekday_group]}, with {q.margin_min:g} minutes to change: "
            f"{_words(self.decision)}."
        ]
        if self.explanations:
            why = " ".join(
                f"{e.sentence} (truth {e.truth:.2f}, based on {e.n} observations)"
                for e in self.explanations
            )
            lines.append(f"Why: {why}")
        if self.crisp_decision is not None or self.crisp_sentences:
            crisp = " ".join(self.crisp_sentences)
            head = (
                f"Official punctuality view: {_words(self.crisp_decision)}."
                if self.crisp_decision is not None
                else "Official punctuality view:"
            )
            lines.append(f"{head} {crisp}".rstrip())
        if self.provenance.fallback:
            lines.append(
                "Note: this is based on arrival delays only, because too few matching "
                "connections were found."
            )
        lines.append(f"Data period: {self.provenance.period}.")
        return "\n".join(lines)


_WEEKDAY_TEXT: dict[str, str] = {
    "weekday": "on weekdays",
    "monday": "on Mondays",
    "friday": "on Fridays",
    "weekend": "at weekends",
    "all": "on all days",
}


def _words(key: str) -> str:
    """Config/enum key -> plain words ("morning_peak" -> "morning peak")."""
    return key.replace("_", " ")
