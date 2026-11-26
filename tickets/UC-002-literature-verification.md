---
id: UC-002
title: Verify literature and extract exact quality-measure formulas
epic: research
milestone: M1
status: todo
owner: pm
estimate_h: 3
depends_on: []        # hard: needs merged code
soft_depends_on: []   # soft: interface exists; integrate when merged
agent: none
touches: [docs/literature.md, docs/methods.md, paper/references.bib]
realdata: false
---

## Goal
Every reference marked `to-verify` in docs/literature.md is checked against the source, and
the exact formulas needed by UC-021/UC-022 are written into docs/methods.md with citations.

## Context
UC-022 must not invent Hudec's coverage formula or its parameters. Pincay (2022) book
chapter may already cover regions/quality; that changes how SRQ1 is framed.

## Inputs
docs/literature.md; open-access PDFs (JOS 2018, Informatica 2022, Pincay 2021); library
access for Springer chapters.

## Outputs
- docs/literature.md statuses updated
- docs/methods.md §2–§3: truth formula (protoform 1 and 2) and Hudec coverage / Qc /
  regional measure with equation numbers and parameter values
- paper/references.bib with DOIs (BibTeX keys = keys in docs/literature.md)

## Acceptance criteria
- [ ] No `to-verify` left for keys cited in docs/methods.md
- [ ] Hudec coverage formula, its parameters (r1, r2 or equivalent) and Qc rule copied with
      equation/page reference
- [ ] One paragraph in docs/literature.md: does Pincay (2022) already study regions or
      quality measures? (yes/no + where)
- [ ] One paragraph: what Stat-to-Text code/prompts can be reused (licence noted)
- [ ] references.bib compiles with biber/bibtex (no missing fields)

## Tests
Manual review by Nikhil. `python3 scripts/tickets.py validate` still passes.

## Notes / pitfalls
The JOS paper is cited by Pincay et al. as "2020a, 36(4)" but the DOI resolves to 2018,
34(4); use the DOI version and note the discrepancy.
