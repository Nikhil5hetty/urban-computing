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

## 3. Auto-dispatch (`.github/workflows/dispatch.yml`) — subscriptions only

Runs on your Claude Pro and ChatGPT plans; no API keys.

```
push to main / hourly / manual
        │
        ▼
plan job ── reconcile labels ── select ready tickets (setup first, then critical path)
        │                         caps: total 3, claude 1, codex 2 (repo variables)
        ├──► claude job (matrix)   anthropics/claude-code-action@v1, CLAUDE_CODE_OAUTH_TOKEN
        │      Claude reads AGENTS.md + ticket, implements, runs make check,
        │      pushes branch uc-xxx-slug and opens the PR itself
        └──► codex job (matrix)    opens a DRAFT PR on branch uc-xxx-slug and comments
               "@codex implement this ticket …" (posted as you via DISPATCH_PAT)
               → Codex cloud runs on your ChatGPT plan and pushes to that branch
               → you mark the PR "Ready for review" when Codex is done
        │
        ▼
issue labels: agent:running → agent:review (Claude: PR opened; Codex: PR marked ready)
              → removed when the ticket is done on main
              agent:failed if the job failed or the PR was closed unmerged (no auto-retry)
```

### One-time setup

1. **Refresh issues:** `uv run --no-project --with pyyaml python scripts/bootstrap_github.py
   --repo OWNER/urban-computing --sync-status` (adds hard/soft dependencies to the issues).
2. **Claude token:** run `claude setup-token` on your laptop (log in with your Pro account).
   Add the printed token as repo secret `CLAUDE_CODE_OAUTH_TOKEN`.
3. **Personal access token:** GitHub → Settings → Developer settings → Fine-grained tokens →
   only this repository; *Contents*, *Pull requests*, *Issues*: read and write. Add as repo
   secret `DISPATCH_PAT`. It is needed because events created with the default
   `GITHUB_TOKEN` do not trigger other workflows (no CI on agent PRs), and so the `@codex`
   comment comes from your account.
4. **Codex cloud:** at chatgpt.com/codex connect GitHub, give it access to this repo and
   create an environment for it. Setup script:
   ```bash
   pip install uv && uv sync --extra dev
   ```
   Then on any PR, test once by commenting `@codex say hello` to confirm it responds.
5. **Switch on:** set `enabled: true` in `config/dispatch.yaml` and commit to `main`
   (caps live in the same file). Emergency stop without a commit: repo variable
   `DISPATCH_ENABLED=false`.
6. **Branch protection on `main`** (recommended): require the `ci / check` status and one
   approving review. Agents never merge.
7. First run: Actions → dispatch → *Run workflow* with `dry_run` ticked; check the plan;
   then run without it.

### Manual mode (no automation, same tickets)

`python3 scripts/dispatch.py prompt UC-021 --agent claude` prints the exact prompt. Paste
it into Claude Code (terminal, VM) or the Codex app/CLI. Before you start, add the label
`agent:running` to the ticket's issue so the dispatcher skips it.

### Daily operation

- Merge a reviewed PR → the dispatcher starts whatever just became ready.
- Codex draft PR finished (Codex posted its summary) → review it, mark *Ready for review*,
  merge. Marking it ready frees the Codex slot on the next dispatch run.
- A ticket stuck in `agent:failed`: read the comment, fix the ticket text or the cause,
  remove the label → it is picked up on the next run (merge, hourly, or manual).
- Pause everything: `enabled: false` in config/dispatch.yaml, or variable `DISPATCH_ENABLED=false`.
- Work a ticket locally instead: add `agent:running` to its issue first so the dispatcher
  skips it; open the PR as usual.
- Paste PR links into the claude.ai Project; the PM reviews them against the ticket.

### Usage limits

Everything runs on your subscriptions, so dispatched sessions share the same usage limits
as your own interactive Claude Code / Codex use. Claude Pro limits are tight: one Claude
ticket at a time (up to 80 turns) is the default; raise `DISPATCH_CAP_CLAUDE` only if you
see headroom. If a session stops on a usage limit, the ticket ends in `agent:failed`;
remove the label after the limit resets.

### Known risks

- Several tickets append to `docs/methods.md`; expect small merge conflicts there. Resolve
  by keeping both sections.
- Agents may write tests that pass against mocks but not against the real implementation
  once a soft dependency lands. CI on `main` after each merge catches this; the fix is a
  follow-up ticket for the dependent module.
- `claude_args` tool syntax may need adjusting to your Claude Code version.
