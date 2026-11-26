---
id: UC-010
title: Download Ist-Daten Oct 2026 and service points with checksummed manifest
epic: data
milestone: M1
status: in-progress
owner: agent
estimate_h: 2
depends_on: []        # hard: needs merged code
soft_depends_on: [UC-001]   # soft: interface exists; integrate when merged
agent: codex
touches: [src/urban_computing/data/download.py, scripts/download_data.py, data/MANIFEST.example.json, tests/test_download.py, docs/data.md]
realdata: true
---

## Goal
One command downloads the 28 daily Ist-Daten files (1–28 Oct 2026) and the service-point
file into `data/raw/`, and writes `data/MANIFEST.json` with SHA-256 per file.

## Context
Archive: https://archive.opentransportdata.swiss/ (monthly ZIP of daily files). Naming is
not documented: inspect the archive page, record the exact URL pattern in docs/data.md.
Service points: https://data.opentransportdata.swiss/dataset/service-point-v2
(`actual-date-swiss-service-point.csv`).

## Outputs
- `scripts/download_data.py --period 2026-10-01:2026-10-28 [--dry-run]`
- `data/raw/ist-daten/<original file names>` (unzipped daily CSVs; keep the ZIP too)
- `data/raw/service-points/<original file name>`
- `data/MANIFEST.json` and a committed `data/MANIFEST.example.json` (same schema, fake hashes)
- `src/urban_computing/data/download.py::verify_manifest(path) -> list[str]` (returns
  mismatching files; used by invariant I3)

## Acceptance criteria
- [ ] Re-running does not re-download files whose checksum matches (idempotent)
- [ ] Files in `data/raw/` are made read-only (chmod 444) after download
- [ ] `verify_manifest` returns `[]` on a correct tree and lists a tampered file
- [ ] `--dry-run` prints URLs without downloading
- [ ] docs/data.md records the exact archive URL pattern and file names
- [ ] `make data-download` and `make data-verify` (`--verify` flag) work (docs/REALDATA_RUNS.md A1–A2)

## Tests
`tests/test_download.py` (offline: use a temp dir and a fake file to test manifest
writing/verification; network code mocked). Real run output pasted in PR (`realdata`).

## Notes / pitfalls
Never extract into or modify existing files in data/raw. Unzip to a temp dir, then move.
