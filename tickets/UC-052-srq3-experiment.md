---
id: UC-052
title: "SRQ3 experiment: LLM truthfulness and checker disagreement"
epic: evaluation
milestone: M3
status: todo
owner: agent
estimate_h: 3
depends_on: [UC-042, UC-053]        # hard: needs merged code
soft_depends_on: [UC-040]   # soft: interface exists; integrate when merged
agent: codex
touches: [src/urban_computing/evaluation/srq3.py, tests/test_srq3.py]
realdata: true
---

## Goal
Compute H3a, H3b, H3c from the stored LLM outputs.

## Outputs
- H3a: fuzzy-false share (truth < 0.5) in stats_only + Wilson CI; unverifiable rate
- H3b: difference fuzzy_grounded − stats_only; McNemar on claim slots paired by question
  (slot = k-th claim; unpaired slots reported separately) + Wilcoxon on per-question mean
  truth
- H3c: crisp vs fuzzy checker disagreement rate + Wilson CI, split by disagreement type
- Per-temperature and per-seed breakdown; query_tool condition if UC-043 ran
- 5 annotated example claims (borderline ones) for the paper

## Acceptance criteria
- [ ] Uses `--mock` outputs on the fixture and real outputs on the VM, same code path
- [ ] Pairing rule documented in docs/evaluation.md if changed (decision proposal)
- [ ] All numbers registered in the project runner
- [ ] Checker inputs encode cancelled departures (`b_cancelled`) as connection slack −∞ so they count as missed in both checkers; NaN only for unknown values (PM review of #43)

## Tests
`tests/test_srq3.py` with mock outputs.
