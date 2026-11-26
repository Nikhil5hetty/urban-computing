You are an automated coding agent ({agent}) working on the `urban-computing` repository.

**Ticket:** {id} — {title} (GitHub issue #{issue})
**Spec:** `tickets/{file}`
**Soft dependencies (may still be stubs):** {soft}

Do this, in order:

1. Read `AGENTS.md` completely. Then read `tickets/{file}` and every document it links
   (`docs/PROJECT.md` §5 interfaces, `docs/methods.md`, `docs/data.md` as relevant).
2. Work on this ticket only and stay inside its `touches:` paths. Implement the stubs that
   raise `NotImplementedError("{id}")`. Do not implement stubs that belong to other tickets.
3. Soft dependencies may not be implemented yet: code against their signatures, mock them
   with `monkeypatch`, and build test data with `tests/factories.py`.
4. Never edit `data/raw/`, `uv.lock`, thresholds in `eval/hypotheses.yaml`, or anything
   guarded by `tests/test_interfaces.py`. Do not add dependencies. Do not invent formulas,
   fields or citations: write `TODO(verify)` instead and mention it in your summary.
5. Cover every acceptance criterion with a test or a reproducible command.
   Real-data criteria: provide the command; do not try to download data.
6. Run `make check` until it is green (if the environment has no network, use
   `UV_OFFLINE=1 make check`).
7. Set `status: done` in `tickets/{file}` (or `status: blocked` plus a `## Blocker`
   section if you cannot finish; then stop).
8. {agent_specific}
