---
id: UC-030
title: Assistant Question/Answer contract
epic: assistant
milestone: M1
status: todo
owner: agent
estimate_h: 1
depends_on: [UC-001]
touches: [src/urban_computing/assistant/contract.py, tests/test_contract_models.py]
realdata: false
---

## Goal
Typed request/response models shared by the decision engine, crisp baseline, LLM side,
prototype and evaluation.

## Outputs
pydantic models:
- `Question(hub, arr_line|arr_product, dep_line|dep_product|None, time_band, weekday_group,
  margin_min)` — `weekday_group` in {weekday, monday, friday, weekend, all}
- `Explanation(sentence, quantifier, summarizer, restriction, truth, coverage, quality, n)`
- `Answer(question, decision: Literal["safe","at_risk","risky"], explanations: list,
  crisp_decision, provenance: {period, config_hash, git_sha})`
- `Answer.to_text()` renders a citizen-facing paragraph (English) from fields only

## Acceptance criteria
- [ ] JSON round-trip (model → json → model) is lossless
- [ ] Validation errors for margin ≤ 0, unknown hub, unknown time band
- [ ] `to_text()` never adds facts not in the fields (snapshot tests)

## Tests
`tests/test_contract_models.py`.
