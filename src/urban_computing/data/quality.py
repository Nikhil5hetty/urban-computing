"""Data-quality report and invariant I5 (UC-012). INTERFACE stub."""

from __future__ import annotations

from pathlib import Path


def build_quality_report(
    interim_dir: Path, config_path: Path, out_md: Path, out_json: Path
) -> dict:
    """Write docs/data-quality.md + data/interim/quality.json; return the JSON dict.

    The dict contains at least {"I5": {"value": float, "pass": bool}, "filters": [...]}.
    """
    raise NotImplementedError("UC-012")
