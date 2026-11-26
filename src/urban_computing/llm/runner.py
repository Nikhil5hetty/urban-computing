"""LLM runner for UBELIX (UC-040). Stub. Heavy imports must stay inside functions."""

from __future__ import annotations

from pathlib import Path


def run(
    questions_path: Path,
    condition: str,
    model_id: str,
    temperature: float,
    seed: int,
    out_dir: Path,
    mock: bool = False,
) -> Path:
    """Generate outputs as JSONL (one line per question); resumable; `mock` for CI."""
    raise NotImplementedError("UC-040")
