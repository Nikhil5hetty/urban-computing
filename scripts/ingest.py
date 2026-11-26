"""Ingest local daily Ist-Daten CSVs using the study configuration."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from urban_computing.data.ingest import ingest_all


def main() -> None:
    """Write daily Parquet files and print the number of records ingested."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/study.yaml"))
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--interim-dir", type=Path)
    args = parser.parse_args()
    data = yaml.safe_load(args.config.read_text(encoding="utf-8"))["data"]
    raw_dir = args.raw_dir or Path(data["raw_dir"])
    interim_dir = args.interim_dir or Path(data["interim_dir"])
    try:
        reports = ingest_all(raw_dir, interim_dir / "ist")
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(f"Ingested {sum(report.rows_out for report in reports):,} rows from {len(reports)} CSVs.")


if __name__ == "__main__":
    main()
