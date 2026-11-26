---
id: UC-022
title: Hudec coverage, quality Qc and regional quality
epic: fuzzy
milestone: M1
status: todo
owner: agent
estimate_h: 3
depends_on: [UC-021, UC-002]
touches: [src/urban_computing/fuzzy/quality.py, tests/test_quality.py, docs/methods.md]
realdata: false
---

## Goal
Implement the quality measures that answer Pincay et al.'s open question ("combine validity
with existing quality measures") exactly as published.

## Inputs
docs/methods.md §3 as filled by UC-002 (formulas, parameters, equation numbers).

## Outputs
- `coverage(mu_R, mu_S, params) -> float`
- `quality_qc(truth, coverage, tnorm="product", c_min=0.5) -> float` (0 if C < c_min)
- `regional_quality(per_region_truths, weights?) -> float` (Hudec et al. 2022)

## Acceptance criteria
- [ ] Formulas match docs/methods.md §3 symbol by symbol; each function's docstring cites
      the equation
- [ ] Worked example(s) from the papers reproduced numerically, if the papers give one
- [ ] Qc = 0 whenever C < c_min; Qc ≤ truth for product t-norm
- [ ] If UC-002 is not done, ticket is `blocked` (do not guess parameters)

## Tests
`tests/test_quality.py`: paper examples, edge cases (no rows in R, all rows in R).
