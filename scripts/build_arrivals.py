"""Build the arrivals Parquet and filter log from local STOP_EVENTS and atlas CSV."""

import argparse
from pathlib import Path

import yaml

from urban_computing.data.arrivals import build_arrivals_file


def main() -> None:
    """Resolve input and output paths from the CLI or study YAML."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/study.yaml"))
    parser.add_argument("--interim-dir", type=Path)
    parser.add_argument("--service-points", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        data = yaml.safe_load(args.config.read_text(encoding="utf-8"))["data"]
        output = build_arrivals_file(
            args.interim_dir or Path(data["interim_dir"]),
            args.service_points
            or Path(data["service_points_dir"]) / "actual-date-swiss-service-point.csv",
            args.config,
            args.out or Path(data["processed_dir"]) / "arrivals.parquet",
        )
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(output)


if __name__ == "__main__":
    main()
