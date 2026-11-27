---
id: UC-013
title: Build the arrivals fact table
epic: data
milestone: M1
status: in-progress
owner: agent
estimate_h: 3
depends_on: [UC-011]        # hard: needs merged code
soft_depends_on: [UC-012]   # soft: interface exists; integrate when merged
agent: codex
touches: [src/urban_computing/data/arrivals.py, scripts/build_arrivals.py, tests/test_arrivals.py, tests/test_contracts.py]
realdata: true
---

## Goal
One row per REAL train arrival at a stop with all attributes needed for restrictions.

## Outputs
`data/processed/arrivals.parquet` with exactly the columns in docs/PROJECT.md §5.

## Acceptance criteria
- [ ] Filters from config/study.yaml applied (REAL status, trains, no extra trips, no
      pass-through); counts in/out logged to `data/processed/arrivals_log.json`
- [ ] `delay_min = (actual_arrival - planned_arrival)` in minutes (float, negative = early)
- [ ] Cancelled journeys kept with `cancelled = true` and `delay_min = null`
- [ ] `canton` joined from service points via SLOID/BPUIC; share of unmatched stops reported
      (< 5% expected for Swiss stops; foreign stops excluded)
- [ ] `time_band`, `weekday`, `half` derived from config/study.yaml (local time)
- [ ] Contract test: columns and dtypes equal PROJECT.md §5
- [ ] `make data-arrivals` works (`scripts/build_arrivals.py`)
- [ ] Rows with planned or actual arrival in the ambiguous DST hour (2026-10-25 02:00–02:59 local) get `delay_min = null` and are counted in `arrivals_log.json`, because their delay can be off by ±60 min (PM review of #45)
- [ ] Same arrival-event definition, cancellation handling and DST window as D-024 (UC-012), so invariant I5 and `arrivals.parquet` count the same arrivals; a test checks agreement on the fixture (PM review of #46)

## Tests
`tests/test_arrivals.py` (fixture: known delays → exact delay_min; band assignment at
boundaries 06:00, 09:00), `tests/test_contracts.py::test_arrivals_schema`.

## Notes / pitfalls
Planned times are minute-rounded, actual times have seconds: a "0.5 min" delay is normal.
Do not round delay_min.
