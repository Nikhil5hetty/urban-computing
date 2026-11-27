---
id: UC-022
title: Hudec coverage, quality Qc and regional quality
epic: fuzzy
milestone: M1
status: done
owner: agent
estimate_h: 3
depends_on: [UC-002]        # hard: needs merged code
soft_depends_on: [UC-021]   # soft: interface exists; integrate when merged
agent: claude
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
- [ ] D-027: `coverage(mu_R, mu_S, params)` reads `mining.coverage_r1/r2` (0.02 / 0.15) and implements hudec2018 Eqs. (A.3)–(A.4) / hudec2022 Eqs. (18)–(19); m_i = 1 iff μ_S > 0 and μ_R > 0, denominator n = all records (UC-002)
- [ ] D-027: `quality_qc` = t(v, C) if C ≥ c_min (0.5) else 0, always with `mining.qc_tnorm` (product), also when the truth ablation uses `tnorm: min` (hudec2018 Eq. (9), p. 987) (UC-002)
- [ ] D-027: change the frozen stub to `regional_quality(per_region_truth, region_sizes) -> dict[str, float]` (ordinal sum, a = 0.5, hudec2022 Eqs. (8), (13)–(16); A = 0 when v_i = 0) and update `tests/test_interfaces.py` in the same PR (AGENTS §4.9) (UC-002)
- [ ] Test vectors from methods §3: C = 0.5377 / 1 / 0 for 175 / 320 / 13 of 2000 records; A = 0.2416 (D1, rounded inputs), 1 (D2), 0 (D3, v = 0), A(1, 0.001) = 0.501 (UC-002)

## Tests
`tests/test_quality.py`: paper examples, edge cases (no rows in R, all rows in R).
