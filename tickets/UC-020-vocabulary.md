---
id: UC-020
title: Fuzzy vocabulary module (membership functions from config)
epic: fuzzy
milestone: M1
status: in-progress
owner: agent
estimate_h: 2
depends_on: []        # hard: needs merged code
soft_depends_on: []   # soft: interface exists; integrate when merged
agent: claude
touches: [src/urban_computing/fuzzy/vocabulary.py, tests/test_vocabulary.py, config/vocabulary.yaml, docs/methods.md]
realdata: false
---

## Goal
Load config/vocabulary.yaml into vectorised membership functions usable by the truth engine.

## Outputs
- `Trapezoid(a, b, c, d)` with `__call__(x: np.ndarray) -> np.ndarray` (null shoulders = ±inf)
- `load_vocabulary(path) -> Vocabulary` exposing `summarizers[attr][word]`,
  `quantifiers[set][word]`, and `late_for_my_transfer(margin_min, spread_min)`
- docs/methods.md §1: final breakpoints + one-line justification each (SBB 3-min boundary,
  Pincay quantifier set, etc.)

## Acceptance criteria
- [ ] Membership exactly 0 at a and d, exactly 1 on [b, c]; linear in between
- [ ] Degenerate shapes allowed (triangles b == c; shoulders with null)
- [ ] Words of one summarizer form a sensible partition: for delays in [-5, 30] min the sum
      of memberships is in [0.99, 1.01] (Ruspini) — or the docs state why not
- [ ] `late_for_my_transfer(m)` is 0 for x ≤ m − spread, 1 for x ≥ m, monotone
- [ ] Changing config/vocabulary.yaml needs no code change
- [ ] No pandas / duckdb import in `fuzzy/`

## Tests
`tests/test_vocabulary.py`: breakpoints, monotonicity of `most`, Ruspini check, invalid
config (a > b) raises `ValueError`.
