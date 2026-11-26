# Evaluation: task level and project level

Two layers. **Task level** decides whether a single ticket/PR is done. **Project level**
decides what the paper may claim.

## 1. Task level

### 1.1 Definition of Done (every ticket)

1. All acceptance criteria in the ticket are met. Each criterion is backed by a named test
   (`tests/test_*.py::test_*`) or a reproducible command whose output is pasted in the PR.
2. `make check` is green (ruff lint + format check, pytest without realdata/gpu markers).
3. Tests are deterministic and offline. Real-data tests carry `@pytest.mark.realdata`;
   GPU tests carry `@pytest.mark.gpu`.
4. Public functions: type hints + docstring with inputs, outputs and **units** (minutes,
   proportions in [0, 1], local time Europe/Zurich).
5. Output files follow the schemas in docs/PROJECT.md §5 and the ticket.
6. Docs named in the ticket are updated. Formulas are cited (paper + equation/page).
7. The ticket file has `status: done`; deviations are listed in the PR description.

### 1.2 Test types we expect

| Type | Where | Example |
|---|---|---|
| Unit | tests/test_<module>.py | trapezoid membership at breakpoints is 0 / 1 exactly |
| Property | same | truth ∈ [0, 1]; quantifier monotone (most) |
| Golden / analytical | same | 80% fully late rows → v("most are late") = μ_most(0.8) |
| Cross-implementation | tests/test_truth_engine.py | NumPy engine vs Simpful (I2) |
| Contract | tests/test_contracts.py | parquet columns/dtypes match PROJECT.md §5 |
| Real-data smoke | `@pytest.mark.realdata` | arrivals for 1 day: delay_min median within [-1, 5] |
| Repo contract | tests/test_repo_contract.py | tickets valid, no cycles, hypotheses schema |

### 1.3 Review checklist (PM)

- Does the code do what the ticket says, and nothing outside `touches:`?
- Are the tests meaningful (would they fail on a plausible bug)?
- Any silent data dropping? Every filter must report counts in/out.
- Any number that will reach the paper: is it produced by code and traceable?

## 2. Project level

### 2.1 Pre-registration

`eval/hypotheses.yaml` lists hypotheses H1a–H3c with metric, statistical test and decision
rules, and invariants I1–I6. It is frozen (D-013). The project runner (UC-053) evaluates
each rule and writes a verdict: `supported`, `not_supported`, or `inconclusive` (neither
rule fires).

### 2.2 Invariants (correctness gates)

Invariants must all pass before any hypothesis verdict is reported. If one fails,
`results/REPORT.md` says so at the top and the paper numbers are not exported.

| ID | Gate |
|---|---|
| I1 | truth engine = analytical values on synthetic data (< 1e-9) |
| I2 | NumPy engine = Simpful membership (< 1e-6) |
| I3 | raw checksums = data/MANIFEST.json |
| I4 | 100% of explanation sentences recompute to their stated truth |
| I5 | crisp punctual share of REAL train arrivals ∈ [0.80, 0.99] |
| I6 | every number in paper/ comes from results.json |

### 2.3 Statistics

- Proportions: Wilson 95% CI. Paired binary outcomes: McNemar (exact if discordant < 25).
- Paired continuous: Wilcoxon signed-rank. Rank agreement: Kendall τ with permutation test.
- Bootstrap (2000 resamples, seed from config) over operating days for stability numbers.
- The 8 hypothesis tests are reported as exploratory; no multiplicity correction
  (stated in the paper).

### 2.4 Ablations (UC-054, reported but not hypotheses)

t-norm (product vs min); β ∈ {0.5, 0.6, 0.7}; summarizer breakpoints ±1 min; core vs
extended quantifiers; min transfer time 1–4 min; LLM temperature 0 vs 0.7.

### 2.5 What the paper may claim

- Only verdicts from results.json, with their CIs.
- "Faithful explanations" only if I4 passes.
- No claims about user understanding or satisfaction (D-004).
- The Pincay re-implementation is called a "methodological baseline", not a reproduction
  of their numbers.

### 2.6 Reproducibility

`make eval-sample` runs the full pipeline on the synthetic fixture in CI. `make eval` on the
real data must regenerate results.json byte-identically for the same data, config and
seed (except timestamps in `meta`). UC-074 runs this from a clean clone.
