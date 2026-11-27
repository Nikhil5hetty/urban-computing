---
id: UC-033
title: Fixed evaluation question set
epic: assistant
milestone: M2
status: todo
owner: agent
estimate_h: 2
depends_on: [UC-031, UC-032]        # hard: needs merged code
soft_depends_on: [UC-014]   # soft: interface exists; integrate when merged
agent: codex
touches: [src/urban_computing/evaluation/questions.py, scripts/make_questions.py, eval/questions.jsonl, tests/test_questions.py]
realdata: true
---

## Goal
A seeded, stratified set of ≥ 120 Questions (hub × time band × weekday group × margin)
drawn from segments that exist in the data. Used by SRQ2, SRQ3 and the prototype demo.

## Outputs
`eval/questions.jsonl` (committed; contains no raw data, only question fields) and
`eval/questions_manifest.json` (seed, strata counts, n per segment).

## Acceptance criteria
- [ ] Every hub, every time band with ≥ 20 connections, and every margin in config appears
- [ ] Only segments with ≥ 20 observations are sampled
- [ ] Same seed → identical file
- [ ] Contains ≥ 15 borderline questions (fuzzy p_miss within ±0.05 of a decision
      boundary), selected by rule, not by hand
- [ ] `make questions` works
- [ ] Hub names and time bands come from `config/study.yaml` (Question validation is exact-match, e.g. "Zürich HB") (PM review of #38)
- [ ] Hub rows are selected by stop identifier using the resolved `config["connections"]["hub_stop_ids"]` (UC-014 normalisation), the same mapping the crisp baseline uses, so fuzzy and crisp answers cover the same arrivals (PM review of #51)

## Tests
`tests/test_questions.py` on the fixture (stratification, determinism).
