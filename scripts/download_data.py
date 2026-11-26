"""Download study inputs or verify their checksummed manifest."""

import argparse
from datetime import date
from pathlib import Path

from urban_computing.data.download import (
    download_ist_daten,
    download_service_points,
    verify_manifest,
    write_manifest,
)


def main() -> int:
    """Run the downloader or verify all listed raw files; return a CLI status."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--period", metavar="START:END", help="inclusive ISO date range")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="print source URLs without fetching")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    if args.verify and args.dry_run:
        parser.error("--dry-run requires --period")
    manifest = args.data_dir / "MANIFEST.json"
    try:
        if args.verify:
            bad = verify_manifest(manifest)
            for path in bad:
                print(f"Missing or mismatching file: {path}")
            if bad:
                return 1
            print(f"Verified {manifest}")
        else:
            start, end = map(date.fromisoformat, args.period.split(":"))
            raw_dir = args.data_dir / "raw"
            files = download_ist_daten(start, end, raw_dir, dry_run=args.dry_run)
            files.append(download_service_points(raw_dir, dry_run=args.dry_run))
            if not args.dry_run:
                write_manifest(files, manifest)
                print(f"Wrote {manifest}")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
