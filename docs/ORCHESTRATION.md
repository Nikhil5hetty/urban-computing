# Orchestration: keeping agents busy without waiting

Three mechanisms remove waiting. Humans (Nikhil, PM) only review and merge.

## 1. Interface-first (hard vs soft dependencies)

Every module already exists as a stub with frozen signatures
(`tests/test_interfaces.py`), table schemas live in `src/urban_computing/data/schemas.py`,
and `tests/factories.py` builds schema-correct test data. So a ticket only waits for
**hard** dependencies (it needs real computation from another ticket). **Soft**
dependencies are coded against the interface and mocked in tests.

`python3 scripts/tickets.py ready` uses hard dependencies only. With nothing merged, 13
agent tickets are ready at once (vs 3 before).

## 2. Real data never blocks a ticket

`realdata: true` tickets finish on the synthetic fixture. The real runs are batched in
`docs/REALDATA_RUNS.md` (Batches A–D, one `make` target per step) and run by Nikhil on the
VM / UBELIX when convenient.

## 3. Auto-dispatch (`.github/workflows/dispatch.yml`)

```
push to main / hourly / manual
        │
        ▼
plan job ── reconcile labels ── select ready tickets (setup first, then critical path)
        │                         caps: total 4, claude 2, codex 2 (repo variables)
        ├──► claude job (matrix)   anthropics/claude-code-action@v1
        │      Claude reads AGENTS.md + ticket, implements, runs make check,
        │      pushes branch uc-xxx-slug and opens the PR itself
        └──► codex_work job (matrix)   openai/codex-action@v1, sandbox ":workspace", no network
               │  exports the diff as an artifact
               ▼
             codex_pr job: fresh runner applies the patch, re-runs make check,
               pushes, opens the PR (draft if make check failed)
        │
        ▼
issue labels: agent:running → agent:review (PR open) → removed when the ticket is done on main
              agent:failed if the job failed or the PR was closed unmerged (no auto-retry)
```

### One-time setup

1. **Labels and issues:** `python3 scripts/bootstrap_github.py --repo OWNER/urban-computing`
   (already done) and, after this change, `--sync-status` to refresh issue bodies with the
   hard/soft dependencies.
2. **Secrets** (Settings → Secrets and variables → Actions → Secrets):
   - `DISPATCH_PAT`: fine-grained personal access token limited to this repo with
     *Contents*, *Pull requests* and *Issues* read/write. Needed because events created
     with the default `GITHUB_TOKEN` do not trigger other workflows, so PRs opened with it
     would not run CI.
   - `CLAUDE_CODE_OAUTH_TOKEN` (run `claude setup-token` locally; uses your Claude
     subscription) **or** `ANTHROPIC_API_KEY`.
   - `OPENAI_API_KEY` (the Codex GitHub Action needs an API key).
3. **Variables** (same page → Variables): `DISPATCH_ENABLED=true`; optionally
   `DISPATCH_CAP`, `DISPATCH_CAP_CLAUDE`, `DISPATCH_CAP_CODEX`.
4. **Branch protection on `main`** (recommended): require the `ci / check` status and one
   approving review. Agents never merge.
5. First run: Actions → dispatch → *Run workflow* with `dry_run` ticked; check the plan;
   then run without it.

### Daily operation

- Merge a reviewed PR → the dispatcher starts whatever just became ready.
- A ticket stuck in `agent:failed`: read the comment, fix the ticket text or the cause,
  remove the label → it is picked up on the next run (merge, hourly, or manual).
- Pause everything: set `DISPATCH_ENABLED=false`.
- Work a ticket locally instead: add `agent:running` to its issue first so the dispatcher
  skips it; open the PR as usual.
- Paste PR links into the claude.ai Project; the PM reviews them against the ticket.

### Costs and limits

Each dispatched ticket is one agent session (Claude: up to 80 turns; Codex: one
`codex exec`). With caps 2 + 2 at most four run at a time. Lower the caps to spend less.

### Known risks

- Several tickets append to `docs/methods.md`; expect small merge conflicts there. Resolve
  by keeping both sections.
- Agents may write tests that pass against mocks but not against the real implementation
  once a soft dependency lands. CI on `main` after each merge catches this; the fix is a
  follow-up ticket for the dependent module.
- `claude_args` tool syntax may need adjusting to your Claude Code version.
