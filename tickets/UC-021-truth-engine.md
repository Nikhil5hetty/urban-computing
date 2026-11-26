---
id: UC-021
title: Truth engine for linguistic summaries (NumPy + Simpful cross-check)
epic: fuzzy
milestone: M1
status: todo
owner: agent
estimate_h: 3
depends_on: [UC-020]
touches: [src/urban_computing/fuzzy/truth.py, tests/test_truth_engine.py, docs/methods.md]
realdata: false
---

## Goal
Compute the truth (validity) of "Q x are S" and "Q R x are S" exactly, fast, and verified
against an independent implementation. Invariants I1 and I2.

## Outputs
- `truth_simple(mu_S: np.ndarray, Q) -> float` = μ_Q(mean(μ_S))
- `truth_restricted(mu_R, mu_S, Q, tnorm="product"|"min") -> float`
  = μ_Q(Σ t(μ_R, μ_S) / Σ μ_R); returns `nan` and flag if Σ μ_R = 0
- `fuzzy_proportion(...)` exposed separately (needed by coverage and the assistant)
- `tests/test_truth_engine.py` with analytical cases and a Simpful cross-check

## Acceptance criteria
- [ ] I1: analytical cases (all-0, all-1, 80% fully-late rows, half membership 0.5 rows,
      restricted case with crisp R) match to < 1e-9
- [ ] I2: memberships from our Trapezoid and from Simpful's equivalent agree to < 1e-6 on a
      grid of 10 000 points per word
- [ ] Property tests: truth ∈ [0, 1]; for monotone Q, adding rows that satisfy S never
      lowers truth
- [ ] 10 million rows evaluated in < 2 s on a laptop (vectorised)
- [ ] docs/methods.md §2 completed with citations (from UC-002 if available; else
      `TODO(verify)` + note in PR)

## Tests
As above. Mark the Simpful test `skipif` Simpful missing, but CI must have it (UC-001).
