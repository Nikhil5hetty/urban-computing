---
id: UC-001
title: Lock dependencies and make CI green
epic: setup
milestone: M1
status: done
owner: agent
estimate_h: 1
depends_on: []        # hard: needs merged code
soft_depends_on: []   # soft: interface exists; integrate when merged
agent: codex
touches: [pyproject.toml, uv.lock, Makefile, .github/workflows/ci.yml]
realdata: false
---

## Goal
A fresh clone installs with one command and `make check` passes locally and in CI.

## Context
The scaffold was written offline, so `uv.lock` does not exist yet and versions are unpinned.

## Inputs
pyproject.toml, Makefile, .github/workflows/ci.yml.

## Outputs
`uv.lock` committed; CI workflow passing on `main`.

## Acceptance criteria
- [ ] `uv sync --extra dev` succeeds on Python 3.11 and 3.12
- [ ] `make check` passes (existing tests/test_repo_contract.py included)
- [ ] CI runs on pull requests and on push to main and is green
- [ ] `simpful` imports successfully (needed by UC-021)
- [ ] The `llm` extra is NOT installed in CI

## Tests
CI run link in the PR; `make check` output pasted.

## Notes / pitfalls
Do not add packages beyond what tickets need. If a pinned version fails, pin the nearest
working one and note it in the PR.
