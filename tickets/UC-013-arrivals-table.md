---
id: UC-013
title: Build the arrivals fact table
epic: data
milestone: M1
status: todo
owner: agent
estimate_h: 3
depends_on: [UC-011, UC-012]
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

## Tests
`tests/test_arrivals.py` (fixture: known delays → exact delay_min; band assignment at
boundaries 06:00, 09:00), `tests/test_contracts.py::test_arrivals_schema`.

## Notes / pitfalls
Planned times are minute-rounded, actual times have seconds: a "0.5 min" delay is normal.
Do not round delay_min.
