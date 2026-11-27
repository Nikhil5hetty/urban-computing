---
id: UC-072
title: "Paper: empirical study, discussion, limitations, conclusion, abstract, GenAI declaration"
epic: paper
milestone: M4
status: todo
owner: agent
estimate_h: 4
depends_on: [UC-050, UC-051, UC-052, UC-071]        # hard: needs merged code
soft_depends_on: []   # soft: interface exists; integrate when merged
agent: claude
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
- [ ] Limitations state that SRQ2 connections exclude pairs with a cancelled feeder train and treat DST-hour pairs on 2026-10-25 as unknown (D-025) (PM review of #50)
- [ ] Discussion reports I4's `vocabulary_gap_answers`: how often no core quantifier reaches β for p_miss (gaps [0.21, 0.38] ∪ [0.62, 0.70]) and the assistant falls back to the measured share (D-029) — a limitation of the three-word vocabulary (PM review of #56)
- [ ] Re-take `paper/figures/app_*.png` with `app/screenshots.py` on real data (not the synthetic fixture, which shows a warning banner), and the chatbot view once UC-040 / UC-033 cached outputs exist (PM review of #58)
- [ ] Replace the three `% TODO(verify)` comments left by UC-071 with citations now in docs/literature.md: intro 3-minute rule → `bav2026` (§1, p. 3); related §2.1 CWW / Perceptual Computer → `zadeh1996`, `mendel2010`; prototype design-science framing → `hevner2004` (PM follow-up of #64)

## Tests
I6 checker; LaTeX builds.
