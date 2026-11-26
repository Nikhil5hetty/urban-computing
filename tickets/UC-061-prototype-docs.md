---
id: UC-061
title: Prototype installation guide and user manual (paper appendix)
epic: prototype
milestone: M3
status: todo
owner: agent
estimate_h: 1
depends_on: [UC-060]
touches: [docs/INSTALL.md, docs/USER_MANUAL.md, paper/appendix.tex]
realdata: false
---

## Goal
Seminar guidelines require prototype documentation (install + user manual) in an appendix.

## Acceptance criteria
- [ ] INSTALL: from clean machine to running app on the fixture in ≤ 5 commands; tested by
      following it in a fresh container (commands + output in PR)
- [ ] USER_MANUAL: each screen with screenshot and what each number means (truth,
      coverage, n) in plain language
- [ ] paper/appendix.tex generated or written from these two files
