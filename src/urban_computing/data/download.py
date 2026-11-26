"""Raw data download + manifest (UC-010). INTERFACE stub."""

from __future__ import annotations

from datetime import date
from pathlib import Path


def download_ist_daten(start: date, end: date, raw_dir: Path, dry_run: bool = False) -> list[Path]:
    """Download daily Ist-Daten files for [start, end] into raw_dir (read-only afterwards)."""
    raise NotImplementedError("UC-010")


def download_service_points(raw_dir: Path, dry_run: bool = False) -> Path:
    """Download the atlas v2 service-point file into raw_dir."""
    raise NotImplementedError("UC-010")


def write_manifest(files: list[Path], manifest_path: Path) -> None:
    """Write data/MANIFEST.json: path, url, sha256, bytes, downloaded_at per file."""
    raise NotImplementedError("UC-010")


def verify_manifest(manifest_path: Path) -> list[str]:
    """Return paths whose current SHA-256 differs from the manifest (invariant I3)."""
    raise NotImplementedError("UC-010")
