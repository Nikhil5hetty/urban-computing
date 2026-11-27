---
id: UC-032
title: Crisp official-view baseline decision
epic: assistant
milestone: M2
status: in-progress
owner: agent
estimate_h: 1
depends_on: []        # hard: needs merged code
soft_depends_on: [UC-014, UC-030, UC-013]   # soft: interface exists; integrate when merged
agent: claude
touches: [src/urban_computing/assistant/crisp.py, tests/test_crisp.py]
realdata: false
---

## Goal
The answer an official-statistics view gives for the same Question: uses the SBB rule
(< 3 min = punctual, D-007) on the arriving train and ignores the passenger's margin.

## Rule
p_late_crisp = share of the arriving line's REAL arrivals at the hub with delay ≥ 3 min.
Crisp decision: safe if p < 0.075, at_risk if 0.075 ≤ p < 0.25, risky if p ≥ 0.25
(the crossover points of the fuzzy decision words in UC-031, so only crispness and margin
differ). Crisp sentences use "most" = more than half (D-012).

## Acceptance criteria
- [ ] Returns the same `Answer` type with `crisp_decision` filled and crisp sentences
- [ ] Independent of `margin_min` (test asserts this)
- [ ] Thresholds read from config, mirrored in docs/methods.md §5

## Tests
`tests/test_crisp.py`.
