---
id: UC-040
title: LLM runner on UBELIX (Apertus-8B, stats-only and fuzzy-grounded)
epic: llm
milestone: M2
status: todo
owner: agent
estimate_h: 4
depends_on: [UC-033]
touches: [src/urban_computing/llm/runner.py, src/urban_computing/llm/prompts.py, slurm/run_llm.sbatch, scripts/run_llm.py, tests/test_prompts.py, docs/methods.md]
realdata: true
---

## Goal
For each question, ask the local LLM to write a short citizen answer with quantified
claims, in two conditions, with fixed seeds, and store raw outputs.

## Conditions
- `stats_only`: prompt contains n, mean, median, P90 delay, share ≥ 3 min, share of
  missed connections (crisp) for the segment.
- `fuzzy_grounded`: prompt contains the assistant's Answer (decision + explanation
  sentences with truth) and the instruction to use only supported statements.
Both: answer in ≤ 3 sentences, using only quantifiers {few, about half, most} and words
{on time, slightly late, late, very late, missed, tight, comfortable}; output JSON
`{"claims": [{"quantifier", "summarizer", "restriction"}], "text": "..."}` plus free text.

## Outputs
`data/interim/llm/<condition>/<model>/<temp>/<seed>.jsonl` (gitignored) with prompt hash,
raw output, parse status, timing; `slurm/run_llm.sbatch`.

## Acceptance criteria
- [ ] Model id verified on Hugging Face and recorded with revision hash (config/study.yaml)
- [ ] Prompts are templates in `prompts.py`; snapshot-tested; no data hard-coded
- [ ] Temperatures 0.0 and 0.7, seeds from config; reruns with temp 0 give identical output
- [ ] Runs resume after interruption (skip finished question ids)
- [ ] `--mock` mode produces deterministic fake outputs for CI and for UC-041/042 tests
- [ ] Heavy imports only inside functions (CI has no torch)

## Tests
`tests/test_prompts.py` (rendering, JSON schema in prompt); `@pytest.mark.gpu` smoke test.

## Notes / pitfalls
Use transformers or vLLM, whichever runs on the UBELIX GPU partition; document the module
loads in the sbatch file. Do not send data to any external API.
