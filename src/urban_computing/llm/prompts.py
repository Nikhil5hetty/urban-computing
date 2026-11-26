"""Prompt templates for SRQ3 (UC-040). Stub."""

from __future__ import annotations

from urban_computing.assistant.contract import Answer, Question

CONDITIONS = ("stats_only", "fuzzy_grounded", "query_tool")


def render_prompt(
    condition: str, question: Question, stats: dict | None = None, answer: Answer | None = None
) -> str:
    """Deterministic prompt text for one question and condition."""
    raise NotImplementedError("UC-040")
