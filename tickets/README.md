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
| `depends_on` | ticket ids that must be `done` first |
| `touches` | paths the ticket may create/modify (keep PRs inside them) |
| `realdata` | `true` if acceptance needs data/raw (run on VM/UBELIX) |

## Body sections

Goal · Context · Inputs · Outputs · Acceptance criteria (checkboxes, each testable) ·
Tests · Notes / pitfalls.

## Commands

```
python3 scripts/tickets.py validate   # schema, unique ids, deps exist, no cycles
python3 scripts/tickets.py ready      # todo tickets whose deps are all done
python3 scripts/tickets.py graph      # dependency list per milestone
```
