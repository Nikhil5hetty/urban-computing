---
name: New ticket (create the spec file first)
about: Tickets are specified in tickets/UC-xxx-*.md and synced by scripts/bootstrap_github.py
title: "UC-xxx: "
labels: []
---

Do not specify work here. Add `tickets/UC-xxx-<slug>.md` (see `tickets/README.md`),
run `python3 scripts/tickets.py validate`, then `python3 scripts/bootstrap_github.py --sync-status`.
