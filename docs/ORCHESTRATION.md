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
        │                         caps: config/dispatch.yaml (codex 0: runs locally)
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
   **Status (26 Nov 2026):** non-review `@codex` comments get "To use Codex here, create
   an environment for this repo" although the environment exists (known Codex issue,
   openai/codex#20093). The cloud Codex job is therefore off (`caps.codex: 0`) and Codex
   tickets run through the local runner below.
5. **Switch on:** set `enabled: true` in `config/dispatch.yaml` and commit to `main`
   (caps live in the same file). Emergency stop without a commit: repo variable
   `DISPATCH_ENABLED=false`.
6. **Branch protection on `main`** (recommended): require the `ci / check` status and one
   approving review. Agents never merge.
7. First run: Actions → dispatch → *Run workflow* with `dry_run` ticked; check the plan;
   then run without it.

### Agent lanes (D-020)

Claude and Codex work in parallel, so each ticket has a fixed `agent:` (no `any`) and the two
lanes never touch the same path (`tests/test_lanes.py` fails otherwise). Within a lane, tickets
may share files (e.g. `docs/methods.md` in the Claude lane), because each agent works one
ticket at a time.

| Lane | Tickets | Paths |
|---|---|---|
| Claude (cloud dispatcher) | UC-020–023, 030, 031, 032, 041, 042, 060, 061, 070, 071, 072 | `fuzzy/`, `assistant/`, `llm/parser.py`, `llm/checkers.py`, `evaluation/segments.py`, `app/`, `paper/`, `docs/methods.md`, `config/vocabulary.yaml`, `config/lexicon.yaml` |
| Codex (local runner) | UC-001, 004, 010–014, 024, 033, 040, 043, 050–054, 074 | `pyproject.toml`, `uv.lock`, CI, `data/`, `tests/fixtures/`, `evaluation/` (except `segments.py`), `llm/runner.py`, `llm/prompts.py`, `llm/query_tool.py`, `slurm/`, `docs/data.md`, `docs/llm.md`, `config/study.yaml` |

To move a ticket to the other lane, change its `agent:` and run `make check`; the lane test
tells you which paths would then be shared.

### Local Codex runner (`scripts/codex_local.py`)

Runs Codex tickets one at a time on your machine with the Codex CLI and your ChatGPT login
(`codex login`; the binary bundled with the VS Code extension is found automatically, or set
`CODEX_BIN`). Needs `uv` and `gh` (logged in).

```
make codex-next        # next ready Codex ticket -> PR, then stop
make codex-loop        # repeat until nothing is ready (stops at the first failure)
uv run --no-project --with pyyaml python scripts/codex_local.py --dry-run | --ticket UC-004
```

Per ticket: pick from `origin/main` (agent `codex` or `any`; same order and labels as the
dispatcher; skipped while another Codex ticket is `agent:running`) → worktree in
`../urban-computing-codex-runs/<branch>` (your checkout is untouched) → commit
`status: in-progress` → `uv sync --extra dev` → `codex exec` (workspace-write sandbox, no
network, told not to use git) → the runner checks ticket status `done`, `make check` green
and nothing staged under `data/` → commit, push, `gh pr create` with Codex's final message as
body (files outside `touches:` are listed as warnings) → `agent:review`.
`uv.lock` is committed only by tickets that list it in `touches:`.
On failure: `agent:failed`, nothing pushed, worktree and logs kept in
`../urban-computing-codex-runs/` (the message says how to clean up and retry). A ticket
Codex sets to `blocked` is pushed as a draft PR so you can read the blocker.
Because Codex PRs are opened with your `gh` login, CI runs on them as usual.

### Manual mode (no automation, same tickets)

`python3 scripts/dispatch.py prompt UC-021 --agent claude` prints the exact prompt. Paste
it into Claude Code (terminal, VM) or the Codex app/CLI. Before you start, add the label
`agent:running` to the ticket's issue so the dispatcher skips it.

### Daily operation

- Merge a reviewed PR → the dispatcher starts whatever just became ready.
- Codex: run `make codex-next` (or `make codex-loop`) after merging; review and merge its PRs.
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
