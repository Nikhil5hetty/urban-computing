---
id: UC-070
title: Paper skeleton (acmart) and numbers export from results.json
epic: paper
milestone: M3
status: in-progress
owner: agent
estimate_h: 2
depends_on: []        # hard: needs merged code
soft_depends_on: [UC-053]   # soft: interface exists; integrate when merged
agent: claude
touches: [paper/, scripts/export_paper_numbers.py, tests/test_export_numbers.py]
realdata: false
---

## Goal
ACM acmart single-column manuscript skeleton following the Human-IST seminar guidelines,
with every number injected from results.json (invariant I6).

## Outputs
- `paper/main.tex` (acmart manuscript, author-year citations), sections: Introduction,
  Background & Related Work, Concept (CWW assistant design), Prototype, Empirical Study
  (Data, SRQ1–3), Discussion, Limitations, Conclusion, GenAI declaration, Appendix
- `scripts/export_paper_numbers.py` → `paper/numbers.tex` with macros like
  `\HoneaPoint`, `\HoneaCI` (names derived deterministically from hypothesis ids)
- `scripts/check_paper_numbers.py`: fails if a digit sequence with a decimal point appears
  in paper/*.tex outside numbers.tex/tables/ (I6)

## Acceptance criteria
- [ ] `latexmk -pdf paper/main.tex` builds (in CI only if TeX available; else documented)
- [ ] Abstract placeholder ~150 words + keywords; ≤ 3 heading levels
- [ ] I6 checker implemented and registered as invariant in the runner
- [ ] `make paper-numbers` works

## Tests
`tests/test_export_numbers.py` (macro names, values from a sample results.json, I6 checker).
