"""Pure render helpers for the prototype (UC-060). Stub."""

from __future__ import annotations

from urban_computing.assistant.contract import Answer


def truth_badge(truth: float) -> str:
    """'green' if truth >= 0.6, 'amber' if 0.3 <= truth < 0.6, else 'red'."""
    raise NotImplementedError("UC-060")


def answer_view_model(ans: Answer) -> dict:
    """Everything the UI displays, derived only from the Answer."""
    raise NotImplementedError("UC-060")
