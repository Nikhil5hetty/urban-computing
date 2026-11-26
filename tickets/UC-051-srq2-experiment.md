---
id: UC-051
title: "SRQ2 experiment: crisp official view vs perception-aware verdicts"
epic: evaluation
milestone: M2
status: todo
owner: agent
estimate_h: 3
depends_on: [UC-031, UC-032, UC-033, UC-053]
touches: [src/urban_computing/evaluation/srq2.py, tests/test_srq2.py]
realdata: true
---

## Goal
Compute H2a and H2b: how often the crisp decision (UC-032) and the fuzzy
perception-aware decision (UC-031) differ across (connection type × margin) cells.

## Outputs
- H2a flip rate + Wilson CI; flip matrix (crisp word × fuzzy word)
- H2b flip rate short (≤ 4 min) minus long (≥ 6 min) + Fisher exact p
- Sensitivity: flip rate for min transfer 1–4 min (ablation, not a hypothesis)
- Three concrete citizen examples ("Official view: safe. For your 4-minute transfer: at risk,
  because …") for the paper and slides

## Acceptance criteria
- [ ] Cells defined from eval/questions.jsonl, not ad hoc
- [ ] Flip definition: crisp decision word ≠ fuzzy decision word
- [ ] Fixture borderline segment produces a flip

## Tests
`tests/test_srq2.py`.
