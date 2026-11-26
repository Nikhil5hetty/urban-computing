---
id: UC-072
title: "Paper: empirical study, discussion, limitations, conclusion, abstract, GenAI declaration"
epic: paper
milestone: M4
status: todo
owner: agent
estimate_h: 4
depends_on: [UC-050, UC-051, UC-052, UC-071]
touches: [paper/sections/data.tex, paper/sections/results.tex, paper/sections/discussion.tex, paper/sections/conclusion.tex, paper/sections/genai.tex, paper/main.tex]
realdata: false
---

## Goal
Practical part of the paper: the empirical study and its interpretation, written only from
results.json and docs/data-quality.md.

## Content requirements
- Data section from docs/data-quality.md (filters and counts)
- One subsection per SRQ: hypothesis, metric, verdict, CI, citizen example
- Discussion: what the verdicts mean for citizens, operators, open-data portals;
  connection to Pincay's open questions
- Limitations (at least): REAL coverage per operator; reconstructed connections and
  assumed transfer time; no passenger counts; one LLM; UK-based perception motivation;
  no user study (D-004); exploratory tests without multiplicity correction
- GenAI declaration: models used (names/versions) and for what (code via Codex / Claude
  Code; PM; writing assistance)

## Acceptance criteria
- [ ] Every verdict matches results.json (including `inconclusive` / `not_supported`)
- [ ] Total paper 16–30 pages incl. appendix
- [ ] Nikhil reviewed and approved

## Tests
I6 checker; LaTeX builds.
