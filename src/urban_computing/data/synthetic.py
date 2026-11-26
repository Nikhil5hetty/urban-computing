"""Synthetic Ist-Daten generator with known ground truth (UC-004). INTERFACE stub."""

from __future__ import annotations

from pathlib import Path


def generate(out_dir: Path, seed: int = 20261126, separator: str = ";") -> Path:
    """Write a tiny Ist-Daten v2-format sample plus ground_truth.json into `out_dir`.

    Returns the directory written. Same seed -> byte-identical files. See UC-004.
    """
    raise NotImplementedError("UC-004")
