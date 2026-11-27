---
id: UC-051
title: "SRQ2 experiment: crisp official view vs perception-aware verdicts"
epic: evaluation
milestone: M2
status: done
owner: agent
estimate_h: 3
depends_on: [UC-031, UC-032, UC-053]        # hard: needs merged code
soft_depends_on: [UC-033]   # soft: interface exists; integrate when merged
agent: codex
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

## Real-data run

On the real-data machine with the Batch A outputs in place, generate the fixed question
set with `make questions` if it is missing. Run the SRQ2 providers and the runner's
required invariants with:

```sh
uv run --locked python -m urban_computing.evaluation.run --config config/study.yaml --only srq2
```

Read H2a (including the flip matrix) and H2b in `results/results.json`. The transfer-time
sensitivity and the first three available flipped cells with their original explanations
are in `results/tables/srq2_transfer_sensitivity.csv` and `results/tables/srq2_examples.csv`.
