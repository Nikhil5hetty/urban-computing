---
id: UC-004
title: Synthetic Ist-Daten fixture generator with known ground truth
epic: setup
milestone: M1
status: todo
owner: agent
estimate_h: 2
depends_on: []        # hard: needs merged code
soft_depends_on: [UC-001]   # soft: interface exists; integrate when merged
agent: codex
touches: [tests/fixtures/, src/urban_computing/data/synthetic.py, tests/test_synthetic.py]
realdata: false
---

## Goal
A deterministic generator that writes small CSV files in the exact Ist-Daten v2 format,
with delays drawn so that the true proportions of fuzzy words are known analytically.
CI and `make eval-sample` run on this instead of real data.

## Inputs
docs/data.md (field list, timestamp formats, status values).

## Outputs
- `src/urban_computing/data/synthetic.py::generate(out_dir, seed) -> Path`
- `tests/fixtures/ist_sample/` (3 operating days, ≤ 200 KB total) + `ground_truth.json`
- Includes: two hubs ("Zürich HB", "Olten"), 3 lines, both products IC and S, REAL plus
  some ESTIMATED/FORECAST/UNKNOWN rows, 1 cancelled journey, 1 pass-through row, 1
  "departure before arrival" anomaly, non-zero-padded BETRIEBSTAG values.

## Acceptance criteria
- [ ] Same seed → byte-identical files
- [ ] Columns and formats match docs/data.md exactly (separator chosen to match the real
      files; if unknown yet, make it a parameter defaulting to `;`)
- [ ] `ground_truth.json` lists, per segment, exact counts of delays in each crisp band and
      planned A→B connections at the hubs with their actual gaps
- [ ] At least one segment is constructed to be a **borderline** case (e.g. 52% of arrivals
      ≥ 3 min late) so crisp and fuzzy verdicts differ (used by SRQ2/SRQ3 tests)

## Tests
`tests/test_synthetic.py`: determinism, schema, ground-truth counts recomputed from files.
