---
id: UC-071
title: "Paper: introduction, related work, concept, prototype sections"
epic: paper
milestone: M4
status: todo
owner: agent
estimate_h: 4
depends_on: [UC-002]        # hard: needs merged code
soft_depends_on: [UC-070, UC-060]   # soft: interface exists; integrate when merged
agent: claude
touches: [paper/sections/intro.tex, paper/sections/related.tex, paper/sections/concept.tex, paper/sections/prototype.tex, paper/references.bib]
realdata: false
---

## Goal
Concept part of the paper (guidelines: concept + practical part).

## Content requirements
- Intro: citizen problem (official crisp punctuality vs perceived reliability), RQs
  verbatim from docs/PROJECT.md, contributions
- Related work: CWW/Perceptual Computer; linguistic summaries (Yager, Kacprzyk & Zadrożny,
  Hudec quality); Pincay et al. 2021/2022 and Human-IST CWW work; LS as XAI (Wrede 2023,
  PLENARY 2022); LLM verification of quantified statements (Eida 2026) and LLM + LS
  (Gaitán-Guerrero 2025); passenger punctuality perception
- Concept: encoder → CWW engine → decoder mapping; why faithful by construction
- Prototype: screens and design-science framing

## Acceptance criteria
- [ ] Only references with status `verified` in docs/literature.md are cited
- [ ] No numbers typed by hand (I6)
- [ ] 8–14 pages for these sections together

## Tests
`scripts/check_paper_numbers.py` passes; LaTeX builds.
