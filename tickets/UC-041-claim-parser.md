---
id: UC-041
title: Parse LLM output into checkable claims
epic: llm
milestone: M2
status: todo
owner: agent
estimate_h: 2
depends_on: []        # hard: needs merged code
soft_depends_on: [UC-030, UC-020]   # soft: interface exists; integrate when merged
agent: any
touches: [src/urban_computing/llm/parser.py, tests/test_parser.py, config/lexicon.yaml]
realdata: false
---

## Goal
Turn each LLM output into a list of claims (quantifier, summarizer, restriction) that the
checkers can evaluate, or mark them `unverifiable`.

## Rules
1. Prefer the JSON block; validate against the schema.
2. Fallback: deterministic lexicon (`config/lexicon.yaml`) for free text, e.g. "the
   majority" → most, "a handful" → few, "roughly half" → about half, "punctual" → on time.
3. Anything not mappable → claim with `status: unverifiable` (counted, never dropped).
4. Causal claims ("because of construction") → `unverifiable_causal`.

## Acceptance criteria
- [ ] JSON path and lexicon path both tested on ≥ 30 hand-written examples in tests
- [ ] JSON text that contradicts the free text → both parsed, flagged `inconsistent`
- [ ] No LLM used for parsing (deterministic)
- [ ] Unverifiable rate is a returned statistic

## Tests
`tests/test_parser.py`.
