---
id: UC-011
title: Ingest raw CSV to validated Parquet with DuckDB
epic: data
milestone: M1
status: in-progress
owner: agent
estimate_h: 3
depends_on: [UC-004]        # hard: needs merged code
soft_depends_on: [UC-010]   # soft: interface exists; integrate when merged
agent: codex
touches: [src/urban_computing/data/ingest.py, scripts/ingest.py, tests/test_ingest.py, docs/data.md]
realdata: true
---

## Goal
Convert each daily CSV into a typed Parquet file in `data/interim/ist/` without dropping or
changing any row, and report schema problems.

## Inputs
`data/raw/ist-daten/*.csv` (or the fixture), docs/data.md.

## Outputs
- `data/interim/ist/<YYYY-MM-DD>.parquet`, columns = raw columns in snake_case plus parsed
  `planned_arrival`, `actual_arrival`, `planned_departure`, `actual_departure` (timestamp,
  Europe/Zurich), `operating_day` (date), booleans for `*_TF` (null → false)
- `data/interim/ingest_report.json`: per file rows_in, rows_out, parse failures by column,
  detected separator/encoding, distinct status values

## Acceptance criteria
- [ ] rows_out == rows_in for every file (no silent drops; unparsable timestamps → null +
      counted)
- [ ] Separator and encoding detected, not hard-coded; recorded in the report
- [ ] Handles non-zero-padded dates (e.g. `1.10.2026`) and both 7/9-digit BPUIC and SLOID
- [ ] Runs with bounded memory (DuckDB streaming; never loads a full day into pandas)
- [ ] Re-running on the same input gives identical Parquet content
- [ ] `make data-ingest` works (`scripts/ingest.py`, defaults from config/study.yaml)
- [ ] Columns mapped by name, not position; leading `_id` (cookbook example) optional; separator detected. On the first real day, the real header is diffed against `tests/fixtures/ist_sample` and the result is recorded in docs/data.md (PM review of #41)
- [ ] Raw daily files are discovered case-insensitively (UC-010 keeps original ZIP names, e.g. `2026-10-12_istdaten.csv`, possibly `.CSV`); the ZIP itself is ignored (PM review of #42)

## Tests
`tests/test_ingest.py` on the UC-004 fixture: row counts, dtypes, null-to-false, parse of
odd dates; one `@pytest.mark.realdata` smoke test on one real day.
