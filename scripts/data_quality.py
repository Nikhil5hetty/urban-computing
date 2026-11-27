"""Generate the data-quality report from local Ist-Daten STOP_EVENTS Parquet."""

import argparse
from pathlib import Path

import yaml

from urban_computing.data.quality import build_quality_report


def main() -> None:
    """Write the two reports and print the I5 verdict."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/study.yaml"))
    parser.add_argument("--interim-dir", type=Path)
    parser.add_argument("--out-md", type=Path, default=Path("docs/data-quality.md"))
    parser.add_argument("--out-json", type=Path)
    args = parser.parse_args()
    data = yaml.safe_load(args.config.read_text(encoding="utf-8"))["data"]
    interim = args.interim_dir or Path(data["interim_dir"])
    try:
        report = build_quality_report(
            interim, args.config, args.out_md, args.out_json or interim / "quality.json"
        )
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    i5 = report["I5"]
    verdict = "PASS" if i5["pass"] else "FAIL"
    print(f"I5 {verdict} ({i5['punctual']:,} of {i5['arrivals']:,} arrivals punctual)")


if __name__ == "__main__":
    main()
