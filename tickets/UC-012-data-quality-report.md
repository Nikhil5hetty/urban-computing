---
id: UC-012
title: Data-quality report (status coverage, anomalies, sanity I5)
epic: data
milestone: M1
status: todo
owner: agent
estimate_h: 2
depends_on: [UC-011]        # hard: needs merged code
soft_depends_on: []   # soft: interface exists; integrate when merged
agent: codex
touches: [src/urban_computing/data/quality.py, scripts/data_quality.py, docs/data-quality.md, tests/test_data_quality.py, config/study.yaml]
realdata: true
---

## Goal
Know exactly how much data survives each filter and whether it is plausible, before any
fuzzy analysis. This report becomes the data section of the paper.

## Outputs
- `docs/data-quality.md` (generated, committed): tables of
  1. rows by PRODUKT_ID and VERKEHRSMITTEL_TEXT (list exact strings; update
     `scope_products` in config/study.yaml via a decision proposal if `Zug` is wrong)
  2. share of AN_PROGNOSE_STATUS values (REAL/ESTIMATED/FORECAST/UNKNOWN/empty) by operator
     and product (D-006)
  3. counts of anomalies: departure before arrival, departure before planned, actual
     arrival > 6 h from planned, empty stop names
  4. crisp punctual share (< 3 min) of REAL train arrivals → invariant I5
- `data/interim/quality.json` (machine-readable version)

## Acceptance criteria
- [ ] Every filter in config/study.yaml has a row-count before/after line
- [ ] I5 computed and its pass/fail stated at the top of the report
- [ ] Operators with < 50% REAL coverage are listed (they bias SRQ1 if kept)
- [ ] Report generation is deterministic and takes < 10 min for 28 days on the VM
- [ ] `make data-quality` works (`scripts/data_quality.py`)
- [ ] Register invariant I5 with `@registry.invariant("I5")` in a module listed in `registry.EXPERIMENT_MODULES` (sample mode uses the fixture); without it the runner blocks every verdict (PM review of #44)

## Tests
`tests/test_data_quality.py` on the fixture (known anomaly counts from ground_truth.json).
