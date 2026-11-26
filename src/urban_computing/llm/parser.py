"""LLM output -> checkable claims (UC-041). Claim is the frozen INTERFACE."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

ClaimStatus = Literal["ok", "unverifiable", "unverifiable_causal", "inconsistent"]


class Claim(BaseModel):
    question_id: str
    slot: int  # k-th claim of the output (pairing key for McNemar, UC-052)
    quantifier: str | None
    summarizer: str | None
    restriction: str | None = None
    status: ClaimStatus = "ok"
    source: Literal["json", "lexicon"] = "json"
    text: str = ""


def parse_output(question_id: str, raw: str, lexicon: dict) -> list[Claim]:
    """Parse JSON block first, lexicon fallback; never drops a claim."""
    raise NotImplementedError("UC-041")
