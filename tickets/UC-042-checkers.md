---
id: UC-042
title: Crisp and fuzzy claim checkers
epic: llm
milestone: M2
status: done
owner: agent
estimate_h: 2
depends_on: [UC-020, UC-021]        # hard: needs merged code
soft_depends_on: [UC-041]   # soft: interface exists; integrate when merged
agent: claude
touches: [src/urban_computing/llm/checkers.py, tests/test_checkers.py, docs/methods.md]
realdata: false
---

## Goal
Score each parsed claim against the segment data twice: crisp truth (Stat-to-Text style,
D-012) and fuzzy truth (our engine). Classify disagreements.

## Outputs
`check(claim, segment_data, vocab) -> {crisp: bool|None, fuzzy: float, fuzzy_true: bool
(truth ≥ 0.5), disagreement: none|crisp_true_fuzzy_false|crisp_false_fuzzy_true}`.

## Crisp truth conditions
most: proportion > 0.5; few: proportion < 0.25 (document; Stat-to-Text has no "few" →
state our choice); about half: |proportion − 0.5| ≤ 0.1; summarizer words crisp via the
SBB 3-min rule and interval midpoints (document each).

## Acceptance criteria
- [ ] Borderline fixture: 52% late → crisp "most are late" true, fuzzy truth < 0.5
- [ ] Every crisp threshold appears in docs/methods.md §6 with source or rationale
- [ ] Checkers are pure functions; 10 000 claims checked in < 5 s

## Tests
`tests/test_checkers.py`.
