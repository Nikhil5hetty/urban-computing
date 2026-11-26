---
id: UC-024
title: Pincay et al. (2021) configuration as methodological baseline
epic: fuzzy
milestone: M1
status: todo
owner: agent
estimate_h: 1
depends_on: [UC-023]        # hard: needs merged code
soft_depends_on: [UC-013]   # soft: interface exists; integrate when merged
agent: any
touches: [src/urban_computing/evaluation/baseline.py, tests/test_baseline.py]
realdata: true
---

## Goal
Run the original configuration (no restrictions, quantifiers few/about half/most, four
delay words, β = 0.6, truth only) network-wide, so SRQ1 can show what changes when quality
and restrictions are added.

## Outputs
`results/tables/baseline_pincay.csv` (12 rows: 3 Q × 4 S, truth, valid flag) via the
evaluation runner, plus the same table per half.

## Acceptance criteria
- [ ] Table has exactly 12 rows per half, layout like Pincay et al. Table 1
- [ ] Paper text calls it a "methodological baseline" (D-003); no comparison of numbers
      with their traffic-message data
- [ ] Registered as an experiment in the project runner (UC-053)

## Tests
`tests/test_baseline.py` on the fixture.
