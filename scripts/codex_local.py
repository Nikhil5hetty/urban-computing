#!/usr/bin/env python3
"""Local Codex runner: works Codex tickets one at a time with the Codex CLI and opens a PR.

Replaces the Codex-cloud hand-off (`@codex` PR comments are unreliable, see
docs/ORCHESTRATION.md). Runs on your machine with your ChatGPT login (`codex login`).

    make codex-next                                   # one ticket, then stop
    make codex-loop                                   # keep going until nothing is ready
    python3 scripts/codex_local.py --dry-run          # only show what would start
    python3 scripts/codex_local.py --ticket UC-004    # a specific ready ticket

Per ticket:
 1. Pick the next ready ticket for Codex (agent: codex or any) from origin/main, using the
    same selection, labels and caps as scripts/dispatch.py (one Codex ticket at a time).
 2. Create a git worktree on branch uc-xxx-slug from origin/main (your checkout is not
    touched), commit `status: in-progress`, run `uv sync --extra dev`.
 3. Run `codex exec` in that worktree (workspace-write sandbox, no network, no git).
 4. Check: ticket status is `done`, `make check` is green, nothing under data/ staged.
 5. Commit, push, `gh pr create` (body = Codex's final message), label agent:review.
On failure the issue gets agent:failed, nothing is pushed (except `blocked`, which is pushed
as a draft PR so you can read the blocker) and the worktree is kept for inspection.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dispatch  # noqa: E402

import tickets as tk  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKDIR = ROOT.parent / f"{ROOT.name}-codex-runs"
ALWAYS_ALLOWED = ("tickets/",)  # the ticket file itself (status changes)


# ---------------------------------------------------------------------------- helpers


def run(cmd: list[str], cwd: Path = ROOT, check: bool = True, **kw) -> subprocess.CompletedProcess:
    """Run a command, echoing it; raise on failure when `check`."""
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd, check=check, text=True, **kw)


def git_out(args: list[str], cwd: Path = ROOT) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, text=True, capture_output=True
    ).stdout.strip()


def find_codex() -> str:
    """Codex CLI path: $CODEX_BIN, PATH, or the binary bundled with the VS Code extension."""
    if os.environ.get("CODEX_BIN"):
        return os.environ["CODEX_BIN"]
    if shutil.which("codex"):
        return shutil.which("codex")  # type: ignore[return-value]
    exts = sorted(Path.home().glob(".vscode/extensions/openai.chatgpt-*/bin/*/codex"))
    if exts:
        return str(exts[-1])
    raise SystemExit("Codex CLI not found: install it or set CODEX_BIN=/path/to/codex")


def snapshot_main(dest: Path) -> Path:
    """Extract tickets/ from origin/main into `dest` (your working copy is not read)."""
    run(["git", "fetch", "--quiet", "origin", "main"])
    blob = subprocess.run(
        ["git", "archive", "origin/main", "tickets"], cwd=ROOT, check=True, capture_output=True
    ).stdout
    with tarfile.open(fileobj=BytesIO(blob)) as tar:
        tar.extractall(dest, filter="data")
    return dest / "tickets"


def outside_touches(files: list[str], touches: list[str]) -> list[str]:
    """Files not covered by the ticket's `touches:` (prefix, exact or glob match)."""
    allowed = [p.rstrip("/") for p in touches]

    def ok(f: str) -> bool:
        if f.startswith(ALWAYS_ALLOWED):
            return True
        return any(f == a or f.startswith(a + "/") or fnmatch.fnmatch(f, a) for a in allowed)

    return [f for f in files if not ok(f)]


def stage_pathspec(touches: list[str]) -> list[str]:
    """Pathspec for `git add`: everything, minus uv.lock unless the ticket owns it."""
    spec = ["-A", "--", "."]
    if "uv.lock" not in touches:
        spec.append(":(exclude)uv.lock")
    return spec


def pr_body(last_message: str, issue: int, warnings: list[str]) -> str:
    body = last_message.strip() or "(Codex left no summary.)"
    if f"#{issue}" not in body:
        body += f"\n\nCloses #{issue}"
    if warnings:
        body += "\n\n### Runner warnings\n" + "\n".join(f"- {w}" for w in warnings)
    return body + "\n\n_Implemented by Codex CLI via `scripts/codex_local.py`._\n"


# ---------------------------------------------------------------------------- selection


def pick_next(only: str | None) -> tuple[dispatch.Pick | None, tk.Ticket | None, str]:
    """Next Codex ticket from origin/main, honouring labels (running/review/failed)."""
    with tempfile.TemporaryDirectory() as tmp:
        tdir = snapshot_main(Path(tmp))
        tickets = tk.load_all(tdir)
        issue_map = json.loads((tdir / "ISSUE_MAP.json").read_text())
    state = dispatch.fetch_state(issue_map)
    if only:
        tickets_sel = [t for t in tickets if t.id == only or t.meta.get("status") == "done"]
    else:
        tickets_sel = tickets
    busy = sum(1 for a in state.running.values() if a == "codex")
    if busy:
        running = [k for k, v in state.running.items() if v == "codex"]
        return None, None, f"a Codex ticket is already agent:running: {running}"
    picks = dispatch.select(
        tickets_sel,
        state,
        issue_map,
        cap_total=len(state.running) + 1,
        cap_agent={"claude": 0, "codex": 1},
    )
    if not picks:
        return None, None, "nothing ready for Codex"
    p = picks[0]
    return p, next(t for t in tickets if t.id == p.id), ""


# ---------------------------------------------------------------------------- one ticket


def work(p: dispatch.Pick, t: tk.Ticket, workdir: Path, codex: str, timeout_min: int) -> bool:
    """Run Codex on one ticket and open its PR. Returns True on success."""
    wt = workdir / p.branch
    logs = workdir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log = logs / f"{p.id}-{stamp}.log"
    last = logs / f"{p.id}-{stamp}.last.md"
    cache = workdir / ".uv-cache"
    env = {**os.environ, "UV_CACHE_DIR": str(cache)}
    touches = list(t.meta.get("touches") or [])

    if git_out(["ls-remote", "--heads", "origin", p.branch]):
        print(f"remote branch {p.branch} exists; resolve it first", file=sys.stderr)
        return False
    if wt.exists():
        print(f"{wt} exists (earlier failed run?); remove it first", file=sys.stderr)
        return False

    dispatch.ensure_state_labels()
    dispatch.set_labels(p.issue, ["agent:codex", "agent:running"], [])
    dispatch.comment(p.issue, f"Dispatched to **codex** (local runner) on branch `{p.branch}`.")

    def fail(reason: str) -> bool:
        print(
            f"FAILED {p.id}: {reason}\nlog: {log}\nworktree kept: {wt}\n"
            f"retry: git worktree remove --force {wt} && git branch -D {p.branch}, "
            f"then remove the agent:failed label on issue #{p.issue}",
            file=sys.stderr,
        )
        dispatch.set_labels(p.issue, ["agent:failed"], ["agent:running"])
        dispatch.comment(
            p.issue,
            f"Local Codex run failed: {reason}. Fix the cause, remove `agent:failed` to retry.",
        )
        return False

    try:
        run(["git", "worktree", "add", "-b", p.branch, str(wt), "origin/main"])
        run(["python3", "scripts/tickets.py", "set-status", p.id, "in-progress"], cwd=wt)
        run(["git", "commit", "-q", "-am", f"{p.id}: start (local Codex runner)"], cwd=wt)
        run(["uv", "sync", "--extra", "dev"], cwd=wt, env=env)

        prompt = dispatch.render_prompt(t, "codex", p.issue, variant="codex_local")
        (logs / f"{p.id}-{stamp}.prompt.md").write_text(prompt)
        cmd = [
            codex, "exec",
            "-C", str(wt),
            "-s", "workspace-write",
            "-c", 'approval_policy="never"',
            "--add-dir", str(cache),
            "-o", str(last),
            "-",
        ]  # fmt: skip
        print(f"running Codex on {p.id} (log: {log}, timeout {timeout_min} min)", flush=True)
        with log.open("w") as fh:
            try:
                res = subprocess.run(
                    cmd, cwd=wt, input=prompt, text=True, stdout=fh, stderr=subprocess.STDOUT,
                    env={**env, "UV_OFFLINE": "1"}, timeout=timeout_min * 60,
                )  # fmt: skip
            except subprocess.TimeoutExpired:
                return fail(f"Codex timed out after {timeout_min} min")
        if res.returncode != 0:
            return fail(f"codex exec exited {res.returncode}")

        status = tk.parse(wt / "tickets" / t.path.name).meta.get("status")
        message = last.read_text() if last.exists() else ""
        run(["git", "add", *stage_pathspec(touches)], cwd=wt)
        files = git_out(["diff", "--cached", "--name-only"], cwd=wt).splitlines()
        keep = (".gitkeep", ".example.json")
        if any(f.startswith("data/") and not f.endswith(keep) for f in files):
            return fail("changes under data/ were staged (hard rule 1/2)")
        if status not in ("done", "blocked"):
            return fail(f"ticket status is `{status}`, expected `done` or `blocked`")
        if status == "done":
            if run(["make", "check"], cwd=wt, env=env, check=False).returncode != 0:
                return fail("`make check` is red after Codex finished")

        warnings = [f"outside `touches:`: `{f}`" for f in outside_touches(files, touches)]
        draft = status == "blocked"
        title = f"{p.id}: {p.title}"
        note = "Implemented by Codex CLI (local runner)."
        run(["git", "commit", "-q", "-m", title, "-m", note], cwd=wt)
        run(["git", "push", "-q", "-u", "origin", p.branch], cwd=wt)
        body = logs / f"{p.id}-{stamp}.pr.md"
        body.write_text(pr_body(message, p.issue, warnings))
        pr_cmd = ["gh", "pr", "create", "--base", "main", "--head", p.branch, "--title", title]
        pr_cmd += ["--body-file", str(body)] + (["--draft"] if draft else [])
        url = run(pr_cmd, cwd=wt, capture_output=True).stdout.strip()
        print(url)
    except subprocess.CalledProcessError as e:
        return fail(f"`{' '.join(map(str, e.cmd))[:120]}` exited {e.returncode}")

    if draft:
        dispatch.set_labels(p.issue, ["agent:failed"], ["agent:running"])
        dispatch.comment(p.issue, f"Codex marked the ticket **blocked**; see draft PR {url}.")
        return False
    dispatch.set_labels(p.issue, ["agent:review"], ["agent:running"])
    dispatch.comment(p.issue, f"codex (local) finished; PR {url} awaits review.")
    run(["git", "worktree", "remove", "--force", str(wt)], check=False)
    return True


# ---------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="only print the next ticket")
    ap.add_argument("--loop", action="store_true", help="continue until nothing is ready")
    ap.add_argument("--ticket", help="run this ticket (must be ready)")
    ap.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    ap.add_argument("--timeout", type=int, default=90, help="minutes per Codex run")
    args = ap.parse_args(argv)

    codex = find_codex()
    while True:
        p, t, why = pick_next(args.ticket)
        if p is None or t is None:
            print(why)
            return 0
        print(f"next: {p.id} ({p.branch}) — {p.title}  [issue #{p.issue}]")
        if args.dry_run:
            return 0
        ok = work(p, t, args.workdir, codex, args.timeout)
        if not ok:
            return 1  # stop: a broken environment would otherwise fail every ticket
        if not args.loop or args.ticket:
            return 0


if __name__ == "__main__":
    sys.exit(main())
