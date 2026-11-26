---
id: UC-074
title: Clean-clone reproducibility check and submission package
epic: paper
milestone: M4
status: todo
owner: agent
estimate_h: 2
depends_on: [UC-072, UC-061, UC-054]        # hard: needs merged code
soft_depends_on: []   # soft: interface exists; integrate when merged
agent: codex
touches: [docs/REPRODUCE.md, scripts/package_submission.py]
realdata: true
---

## Goal
Prove that the reported numbers regenerate from a clean clone, and package the deliverables.

## Acceptance criteria
- [ ] Fresh clone + data download + `make eval` → results.json equal to the reported one
      (except meta.timestamp); diff output pasted in PR
- [ ] All invariants I1–I6 pass in that run
- [ ] `scripts/package_submission.py` builds `submission/` with paper PDF, source zip (no
      data), REPORT.md, INSTALL/USER_MANUAL
- [ ] docs/REPRODUCE.md lists exact commands, hardware, runtimes
