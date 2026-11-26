## Ticket
UC-XXX — Closes #<issue> (number in `tickets/ISSUE_MAP.json`)

## What changed
<!-- 3–6 bullets -->

## How it was tested
<!-- commands you ran and a short summary of their output -->
- [ ] `make check` green
- [ ] `make test-realdata` (only if the ticket has `realdata: true`) — output summary:

## Acceptance criteria
<!-- copy the checklist from the ticket and tick each item; name the test that covers it -->

## Definition of Done (AGENTS.md §6)
- [ ] Changes stay inside the ticket's `touches:` paths (or reasons given below)
- [ ] No files under `data/raw/` written; no data / weights / LLM outputs committed
- [ ] `eval/hypotheses.yaml` thresholds unchanged
- [ ] Docs updated as the ticket requires
- [ ] Ticket file set to `status: done`

## Deviations, decision proposals, `TODO(verify)` items
