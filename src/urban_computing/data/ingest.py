"""Raw CSV -> typed Parquet (UC-011). INTERFACE stub.

Output columns: urban_computing.data.schemas.STOP_EVENTS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class IngestReport:
    source_file: str
    rows_in: int
    rows_out: int
    separator: str
    encoding: str
    parse_failures: dict[str, int] = field(default_factory=dict)
    status_values: dict[str, int] = field(default_factory=dict)


def ingest_day(csv_path: Path, out_dir: Path) -> IngestReport:
    """Convert one daily CSV to data/interim/ist/<YYYY-MM-DD>.parquet. No row is dropped."""
    raise NotImplementedError("UC-011")


def ingest_all(raw_dir: Path, out_dir: Path) -> list[IngestReport]:
    """Ingest every CSV in raw_dir; also writes data/interim/ingest_report.json."""
    raise NotImplementedError("UC-011")
