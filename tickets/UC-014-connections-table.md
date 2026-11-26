---
id: UC-014
title: Reconstruct connections at Zürich HB, Bern, Olten
epic: data
milestone: M1
status: todo
owner: agent
estimate_h: 4
depends_on: [UC-013]
touches: [src/urban_computing/data/connections.py, scripts/build_connections.py, tests/test_connections.py, tests/test_contracts.py, docs/data.md]
realdata: true
---

## Goal
Observed A→B transfer opportunities at three hubs, so the assistant can answer "is my
connection reliable?" (D-009).

## Definition
At hub h, a connection is a pair (A arrives, B departs) of different journeys with planned
gap `planned_dep_B - planned_arr_A` in [2, 15] min (config). Actual gap =
`actual_dep_B - actual_arr_A`. Both need REAL status. Slack = actual gap − min transfer.

## Outputs
`data/processed/connections.parquet` (columns in PROJECT.md §5) and
`data/processed/connections_log.json` (pairs per hub, share with REAL on both sides).

## Acceptance criteria
- [ ] Hub matching by SLOID/number, not by free-text name only; matched ids listed in
      docs/data.md
- [ ] Same journey never paired with itself; A must arrive at h, B must depart from h
- [ ] Cancelled B → connection kept with `actual_gap_min = null` and flagged `b_cancelled`
- [ ] Pair explosion bounded: document pairs per hub per day (expect thousands, not millions)
- [ ] Built with DuckDB range join; < 15 min for 28 days on the VM

## Tests
`tests/test_connections.py` on the fixture: exact pairs and gaps vs ground_truth.json;
boundary gaps 2 and 15 included, 1 and 16 excluded.

## Notes / pitfalls
We do not know which pairs passengers actually use or platform-specific transfer times;
this is a stated limitation. Do not try to infer them.
