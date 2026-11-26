"""Connections at hubs (UC-014). INTERFACE stub. Output: schemas.CONNECTIONS.

Input is STOP_EVENTS (arrivals AND departures are needed), not ARRIVALS.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def build_connections(
    stop_events: pd.DataFrame, hub_stop_ids: dict[str, list[str]], config: dict
) -> pd.DataFrame:
    """Pair arrivals (A) and departures (B) at each hub with planned gap in the config range.

    Pure function on a (small) frame; the file wrapper uses DuckDB for the full month.
    """
    raise NotImplementedError("UC-014")


def build_connections_file(
    interim_dir: Path, service_points_path: Path, config_path: Path, out_path: Path
) -> Path:
    """I/O wrapper writing data/processed/connections.parquet (DuckDB range join)."""
    raise NotImplementedError("UC-014")
