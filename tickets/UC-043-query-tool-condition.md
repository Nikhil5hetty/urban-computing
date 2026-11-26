---
id: UC-043
title: "Stretch: LLM with a query tool (writes DuckDB SQL)"
epic: llm
milestone: M3
status: todo
owner: agent
estimate_h: 4
depends_on: [UC-040]        # hard: needs merged code
soft_depends_on: []   # soft: interface exists; integrate when merged
agent: codex
touches: [src/urban_computing/llm/query_tool.py, src/urban_computing/llm/prompts.py, tests/test_query_tool.py]
realdata: true
---

## Goal
Third condition `query_tool`: the LLM gets the segment schema, writes one SQL query, we run
it read-only in DuckDB on the segment, and the LLM phrases the answer from the result.
Answers the objection "chatbots can query the data themselves".

## Acceptance criteria
- [ ] SQL executed in a sandboxed read-only DuckDB connection on a temp view of the segment
- [ ] Failed/invalid SQL counted (`sql_error_rate`), not retried more than once
- [ ] Outputs stored like UC-040 and checked by UC-042 without code changes there
- [ ] Only start if M2 is done by 2 Dec; otherwise set `status: blocked` with reason "scope"

## Tests
`tests/test_query_tool.py` with mock LLM.
