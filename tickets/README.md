# Tickets

One file per ticket: `UC-xxx-slug.md`. The file is the **spec and the source of truth for
status** (D-016); the GitHub Project board mirrors it.

## Frontmatter

| Field | Meaning |
|---|---|
| `id` | `UC-xxx`, unique |
| `title` | short imperative title (becomes the issue title `UC-xxx: title`) |
| `epic` | setup, research, data, fuzzy, assistant, llm, evaluation, prototype, paper |
| `milestone` | M1 … M4 (see docs/PROJECT.md §6) |
| `status` | `todo`, `in-progress`, `blocked`, `done` |
| `owner` | `agent` (Codex / Claude Code), `nikhil`, or `pm` |
| `estimate_h` | rough effort in hours of agent work |
| `depends_on` | **hard** dependencies: ticket ids whose code must be merged (`done`) first |
| `soft_depends_on` | interface-only dependencies: start now against stubs + `tests/factories.py` |
| `agent` | who the dispatcher starts: `claude`, `codex`, `any` (balanced), `none` (human) |
| `touches` | paths the ticket may create/modify (keep PRs inside them) |
| `realdata` | `true` if the code must also be run on real data; that run is tracked in `docs/REALDATA_RUNS.md` and does not block `done` |

## Body sections

Goal · Context · Inputs · Outputs · Acceptance criteria (checkboxes, each testable) ·
Tests · Notes / pitfalls.

## Commands

```
python3 scripts/tickets.py validate   # schema, unique ids, deps exist, no cycles
python3 scripts/tickets.py ready      # todo tickets whose HARD deps are all done
python3 scripts/tickets.py ready --strict   # also wait for soft deps
python3 scripts/tickets.py graph      # dependency list per milestone
```
