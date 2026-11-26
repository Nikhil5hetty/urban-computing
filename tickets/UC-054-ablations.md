---
id: UC-054
title: Ablations and sensitivity analyses
epic: evaluation
milestone: M3
status: todo
owner: agent
estimate_h: 2
depends_on: [UC-050, UC-051]        # hard: needs merged code
soft_depends_on: []   # soft: interface exists; integrate when merged
agent: codex
touches: [src/urban_computing/evaluation/ablations.py, tests/test_ablations.py]
realdata: true
---

## Goal
Show which conclusions are robust: t-norm (product/min), β ∈ {0.5, 0.6, 0.7}, delay
breakpoints ±1 min, core vs extended quantifiers, min transfer 1–4 min, LLM temperature.

## Outputs
`results/tables/ablations.csv`: one row per (ablation, setting, metric) with the metric
value and whether the hypothesis verdict would change. Not hypotheses; reported as
robustness.

## Acceptance criteria
- [ ] Ablations run from config overrides, not code edits
- [ ] A "verdict_changes" column flags any ablation that flips a pre-registered verdict
- [ ] Runtime documented
- [ ] Ablation: crisp checker with official `late` = delay ≥ 3 min (SBB, D-007) instead of the 0.5-cut partition; report how H3c changes (PM review of #43)

## Tests
`tests/test_ablations.py` on the fixture (override mechanism works).
