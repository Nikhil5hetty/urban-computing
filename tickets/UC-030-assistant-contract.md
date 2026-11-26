---
id: UC-030
title: Assistant Question/Answer contract
epic: assistant
milestone: M1
status: in-progress
owner: agent
estimate_h: 1
depends_on: []        # hard: needs merged code
soft_depends_on: []   # soft: interface exists; integrate when merged
agent: claude
touches: [src/urban_computing/assistant/contract.py, tests/test_contract_models.py]
realdata: false
---

## Goal
Typed request/response models shared by the decision engine, crisp baseline, LLM side,
prototype and evaluation.

## Outputs
The fields of `Question`, `Explanation`, `Provenance` and `Answer` already exist in
`src/urban_computing/assistant/contract.py` (frozen interface). This ticket adds:
- validators: `margin_min > 0`; `hub` in config hubs; `time_band` in config time bands;
  at least one of `arr_line` / `arr_product`
- `Answer.to_text()` rendering a citizen-facing paragraph (English) from fields only

## Acceptance criteria
- [ ] JSON round-trip (model → json → model) is lossless
- [ ] Validation errors for margin ≤ 0, unknown hub, unknown time band
- [ ] `to_text()` never adds facts not in the fields (snapshot tests)

## Tests
`tests/test_contract_models.py`.
