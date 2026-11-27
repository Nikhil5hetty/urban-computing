---
id: UC-050
title: "SRQ1 experiment: coverage, regional masking, ranking change"
epic: evaluation
milestone: M2
status: todo
owner: agent
estimate_h: 3
depends_on: [UC-023, UC-053]        # hard: needs merged code
soft_depends_on: [UC-024, UC-022]   # soft: interface exists; integrate when merged
agent: codex
touches: [src/urban_computing/evaluation/srq1.py, tests/test_srq1.py]
realdata: true
---

## Goal
Compute H1a, H1b, H1c exactly as defined in eval/hypotheses.yaml.

## Outputs (registered in the project runner)
- H1a: share of restricted summaries with v ≥ 0.6 and C < 0.5 + Wilson CI
- H1b: list of stable masking cases (same summarizer, network-wide valid quantifier ≠
  local valid quantifier, in both halves) + count
- H1c: Kendall τ between v-ranking and Qc-ranking of the top-20 restricted summaries
  + permutation p-value (seeded)
- `results/tables/srq1_*.csv`, `results/figures/srq1_*.png`

## Acceptance criteria
- [ ] Metric names and units exactly as in eval/hypotheses.yaml
- [ ] Restriction families used are listed in the output (operator, product, line,
      canton, time band, weekday group)
- [ ] Each masking case has a citizen-readable example sentence pair for the paper
- [ ] Fixture run produces the expected values from ground_truth.json
- [ ] H1a broken down by restriction family and by R's share of the segment (|R|/n). Because i_C ≤ |R|/n, every R below r1 = 2 % of the segment gets C = 0 regardless of truth; report how much of `share_valid_but_low_coverage` comes from such small R, and the same metric for R ≥ 2 %. The pre-registered H1a verdict stays as computed; the breakdown is reported next to it (PM review of #55)
- [ ] H1c: report the Kendall τ also on restricted summaries with |R| ≥ 2 % of the segment, so the ranking change is not only small-R summaries dropping to Qc = 0 (PM review of #55)

## Tests
`tests/test_srq1.py` on the fixture.
