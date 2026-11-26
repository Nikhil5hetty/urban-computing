---
id: UC-053
title: Project-level evaluation runner (make eval / eval-sample)
epic: evaluation
milestone: M2
status: done
owner: agent
estimate_h: 3
depends_on: []        # hard: needs merged code
soft_depends_on: [UC-004, UC-021]   # soft: interface exists; integrate when merged
agent: codex
touches: [src/urban_computing/evaluation/run.py, src/urban_computing/evaluation/registry.py, src/urban_computing/evaluation/stats.py, tests/test_runner.py, tests/test_stats.py]
realdata: false
---

## Goal
One command recomputes every invariant and hypothesis, applies the pre-registered decision
rules, and writes `results/results.json` and `results/REPORT.md`. Build it early as a
skeleton; experiments register themselves as they land.

## Outputs
- `registry.py`: `@experiment("H1a")` / `@invariant("I1")` decorators
- `stats.py`: Wilson CI, McNemar (exact/asymptotic), Wilcoxon, Kendall τ + permutation,
  Fisher exact, bootstrap — thin wrappers over scipy/statsmodels with tests
- `run.py --config config/study.yaml [--sample]`: runs invariants first; if any fails,
  REPORT.md starts with the failure and hypotheses are still computed but marked
  `blocked_by_invariant`
- Verdict logic parses `supported_if` / `not_supported_if` from eval/hypotheses.yaml
  (safe expression evaluator over point, ci_low, ci_high, p, value — no `eval()`)

## Acceptance criteria
- [ ] `make eval-sample` runs in CI in < 2 min and writes both files
- [ ] Hypotheses without a registered experiment → verdict `not_run`
- [ ] Same data + config + seed → identical results.json except `meta.timestamp`
- [ ] results.json schema matches docs/PROJECT.md §5; validated by a test
- [ ] Wilson / McNemar / Kendall wrappers match reference values (statsmodels/scipy docs
      examples) in tests
- [ ] `--only <experiment-module>` runs a subset (used by `make ablations`)

## Tests
`tests/test_runner.py`, `tests/test_stats.py`.
