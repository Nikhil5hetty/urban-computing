"""Arrivals fact table (UC-013). INTERFACE stub. Output: schemas.ARRIVALS."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def build_arrivals(
    stop_events: pd.DataFrame, service_points: pd.DataFrame, config: dict
) -> pd.DataFrame:
    """Filter STOP_EVENTS to REAL train arrivals and derive ARRIVALS columns.

    Pure (no I/O) so it can be tested with tests/factories.py.
    """
    raise NotImplementedError("UC-013")


def build_arrivals_file(
    interim_dir: Path, service_points_path: Path, config_path: Path, out_path: Path
) -> Path:
    """I/O wrapper: read interim Parquet with DuckDB, write data/processed/arrivals.parquet."""
    raise NotImplementedError("UC-013")
