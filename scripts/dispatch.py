#!/usr/bin/env python3
"""Dispatcher: decides which ready tickets to start and on which agent.

Used by .github/workflows/dispatch.yml; also runnable locally.

    python3 scripts/dispatch.py plan --dry-run                  # what would start now
    python3 scripts/dispatch.py plan --mark --output github     # in CI: select + label
    python3 scripts/dispatch.py prompt UC-021 --agent claude    # render the agent prompt
    python3 scripts/dispatch.py finish UC-021 --agent codex --result failure
    python3 scripts/dispatch.py reconcile                       # clean up labels

State lives in GitHub issue labels (ticket -> issue via tickets/ISSUE_MAP.json):
    agent:running   an agent is working on it (counts against the caps); for Codex cloud
                    until you mark its draft PR "Ready for review"
    agent:review    the job opened a PR; waiting for a human merge (does not count)
    agent:failed    the job failed; a human removes the label to allow a retry
    agent:claude / agent:codex   who got it
A ticket is dispatched only if: status todo, owner agent, all HARD deps done, and none of
the three state labels is present.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tickets as tk  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "tickets" / "ISSUE_MAP.json"
PROMPT_PATH = ROOT / ".github" / "agent-prompt.md"
STATE_LABELS = ("agent:running", "agent:review", "agent:failed")
AGENT_NAMES = ("claude", "codex")


@dataclass
class State:
    running: dict[str, str]  # ticket id -> agent
    review: set[str]
    failed: set[str]


@dataclass
class Pick:
    id: str
    agent: str
    title: str
    file: str
    branch: str
    issue: int

    def to_json(self) -> dict:
        return self.__dict__.copy()


# ---------------------------------------------------------------------------- selection


def unblock_counts(tickets: list[tk.Ticket]) -> dict[str, int]:
    """How many tickets (transitively, via hard deps) wait on each ticket."""
    children: dict[str, set[str]] = {t.id: set() for t in tickets}
    for t in tickets:
        for d in t.meta.get("depends_on") or []:
            children.setdefault(d, set()).add(t.id)

    def reach(tid: str, seen: set[str]) -> set[str]:
        for c in children.get(tid, ()):
            if c not in seen:
                seen.add(c)
                reach(c, seen)
        return seen

    return {t.id: len(reach(t.id, set())) for t in tickets}


def branch_for(t: tk.Ticket) -> str:
    return t.path.stem.lower()  # uc-021-truth-engine


def select(
    tickets: list[tk.Ticket],
    state: State,
    issue_map: dict,
    cap_total: int = 4,
    cap_agent: dict[str, int] | None = None,
) -> list[Pick]:
    """Pure selection logic (unit-tested): setup first, then critical path, milestone, id."""
    cap_agent = cap_agent or {"claude": 2, "codex": 2}
    busy = {a: sum(1 for v in state.running.values() if v == a) for a in AGENT_NAMES}
    free_total = cap_total - len(state.running)
    if free_total <= 0:
        return []
    blocked = set(state.running) | state.review | state.failed
    unblocks = unblock_counts(tickets)
    order = list(tk.MILESTONES)
    candidates = [
        t
        for t in tk.ready(tickets)
        if t.meta.get("owner") == "agent" and t.id not in blocked and t.id in issue_map
    ]
    candidates.sort(
        key=lambda t: (
            t.meta["epic"] != "setup",  # setup tickets (lock file, fixtures) always first
            -unblocks[t.id],
            order.index(t.meta["milestone"]),
            t.id,
        )
    )
    picks: list[Pick] = []
    for t in candidates:
        if len(picks) >= free_total:
            break
        want = t.meta["agent"]
        options = AGENT_NAMES if want == "any" else (want,)
        free = {a: cap_agent.get(a, 0) - busy[a] for a in options}
        agent = max(options, key=lambda a: (free[a], a == "claude"))
        if free[agent] <= 0:
            continue
        busy[agent] += 1
        picks.append(
            Pick(
                id=t.id,
                agent=agent,
                title=t.meta["title"],
                file=t.path.name,
                branch=branch_for(t),
                issue=int(issue_map[t.id]["number"]),
            )
        )
    return picks


# ---------------------------------------------------------------------------- GitHub I/O


def gh(args: list[str]) -> str:
    res = subprocess.run(["gh", *args], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)}\n{res.stderr}")
    return res.stdout.strip()


def repo() -> str:
    return os.environ.get("GITHUB_REPOSITORY") or gh(
        ["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]
    )


def load_map() -> dict:
    return json.loads(MAP_PATH.read_text()) if MAP_PATH.exists() else {}


def fetch_state(issue_map: dict) -> State:
    by_number = {int(v["number"]): k for k, v in issue_map.items()}
    out = gh(
        [
            "issue",
            "list",
            "-R",
            repo(),
            "--state",
            "all",
            "--limit",
            "300",
            "--json",
            "number,labels,state",
        ]
    )
    state = State(running={}, review=set(), failed=set())
    for issue in json.loads(out):
        tid = by_number.get(issue["number"])
        if not tid:
            continue
        names = {lab["name"] for lab in issue["labels"]}
        if "agent:running" in names:
            agent = "claude" if "agent:claude" in names else "codex"
            state.running[tid] = agent
        if "agent:review" in names:
            state.review.add(tid)
        if "agent:failed" in names:
            state.failed.add(tid)
    return state


def ensure_state_labels() -> None:
    colors = {
        "agent:running": "1d76db",
        "agent:review": "5319e7",
        "agent:failed": "b60205",
        "agent:claude": "d4c5f9",
        "agent:codex": "c2e0c6",
    }
    for name, color in colors.items():
        gh(["label", "create", name, "--color", color, "--force", "-R", repo()])


def set_labels(issue: int, add: list[str], remove: list[str]) -> None:
    args = ["issue", "edit", str(issue), "-R", repo()]
    for a in add:
        args += ["--add-label", a]
    for r in remove:
        args += ["--remove-label", r]
    gh(args)


def comment(issue: int, body: str) -> None:
    gh(["issue", "comment", str(issue), "-R", repo(), "--body", body])


# ---------------------------------------------------------------------------- prompt


AGENT_SPECIFIC = {
    "claude": (
        "Create branch `{branch}` from `main`. Commit with messages starting `{id}:`. "
        "Push the branch and open a pull request with `gh pr create --title '{id}: {title}'` "
        "whose body follows `.github/pull_request_template.md` and contains "
        "`Closes #{issue}`."
    ),
    "codex": (
        "You are running as a Codex cloud task on the draft pull request for branch "
        "`{branch}` (it already contains a commit setting the ticket to in-progress). Commit "
        "your work to that branch with messages starting `{id}:` and push. Run "
        "`make check` before your final push. In your final message summarise what changed, "
        "how you tested, deviations and TODO(verify) items."
    ),
}


def render_prompt(t: tk.Ticket, agent: str, issue: int) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    fields = {
        "id": t.id,
        "title": t.meta["title"],
        "file": t.path.name,
        "branch": branch_for(t),
        "issue": issue,
        "agent": agent,
        "soft": ", ".join(t.meta.get("soft_depends_on") or []) or "none",
    }
    fields["agent_specific"] = AGENT_SPECIFIC[agent].format(**fields)
    return template.format(**fields)


# ---------------------------------------------------------------------------- commands


def cmd_plan(args: argparse.Namespace) -> int:
    tickets = tk.load_all()
    errs = tk.validate(tickets)
    if errs:
        print("\n".join(errs), file=sys.stderr)
        return 1
    issue_map = load_map()
    if args.dry_run:
        if not issue_map:
            issue_map = {t.id: {"number": 0} for t in tickets}
        running = dict(r.split(":") for r in args.running.split(",") if r) if args.running else {}
        state = State(running=running, review=set(), failed=set())
    else:
        state = fetch_state(issue_map)
    picks = select(
        tickets,
        state,
        issue_map,
        cap_total=args.cap_total,
        cap_agent={"claude": args.cap_claude, "codex": args.cap_codex},
    )
    if args.mark and not args.dry_run:
        ensure_state_labels()
        for p in picks:
            set_labels(p.issue, [f"agent:{p.agent}", "agent:running"], [])
            comment(
                p.issue, f"Dispatched to **{p.agent}** on branch `{p.branch}`. Run: {args.run_url}"
            )
    matrix = {a: [p.to_json() for p in picks if p.agent == a] for a in AGENT_NAMES}
    if args.output == "github":
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            for a in AGENT_NAMES:
                fh.write(f"{a}_matrix={json.dumps(matrix[a])}\n")
                fh.write(f"has_{a}={'true' if matrix[a] else 'false'}\n")
    print(
        f"running: {state.running or '-'}; review: {sorted(state.review) or '-'}; "
        f"failed: {sorted(state.failed) or '-'}"
    )
    for p in picks:
        print(f"start {p.id} on {p.agent} ({p.branch}) — {p.title}")
    if not picks:
        print("nothing to start")
    return 0


def _ticket(tid: str) -> tk.Ticket:
    for t in tk.load_all():
        if t.id == tid:
            return t
    raise SystemExit(f"unknown ticket {tid}")


def cmd_prompt(args: argparse.Namespace) -> int:
    t = _ticket(args.ticket)
    issue = args.issue if args.issue is not None else int(load_map().get(t.id, {}).get("number", 0))
    sys.stdout.write(render_prompt(t, args.agent, issue))
    return 0


def cmd_finish(args: argparse.Namespace) -> int:
    issue = int(load_map()[args.ticket]["number"])
    if args.result == "success":
        set_labels(issue, ["agent:review"], ["agent:running"])
        comment(issue, f"{args.agent} finished; PR {args.pr_url or '(see branch)'} awaits review.")
    else:
        set_labels(issue, ["agent:failed"], ["agent:running"])
        comment(
            issue,
            f"{args.agent} run failed or produced no change ({args.run_url}). "
            "Fix the ticket or the cause, then remove `agent:failed` to retry.",
        )
    return 0


def _pr_for_branch(branch: str) -> dict | None:
    out = gh(
        [
            "pr",
            "list",
            "-R",
            repo(),
            "--state",
            "all",
            "--head",
            branch,
            "--json",
            "state,isDraft,mergedAt,url",
        ]
    )
    prs = json.loads(out)
    return prs[0] if prs else None


def cmd_reconcile(args: argparse.Namespace) -> int:
    """Drop state labels for tickets that are done on main; fail tickets whose PR was
    closed without merging."""
    tickets = {t.id: t for t in tk.load_all()}
    issue_map = load_map()
    state = fetch_state(issue_map)
    for tid in sorted(set(state.running) | state.review):
        issue = int(issue_map[tid]["number"])
        if tickets[tid].meta.get("status") == "done":
            set_labels(issue, [], ["agent:running", "agent:review"])
            continue
        if state.running.get(tid) == "codex":
            pr = _pr_for_branch(branch_for(tickets[tid]))
            if pr and pr["state"] == "OPEN" and not pr["isDraft"]:
                set_labels(issue, ["agent:review"], ["agent:running"])
            elif pr and pr["state"] == "CLOSED" and not pr["mergedAt"]:
                set_labels(issue, ["agent:failed"], ["agent:running"])
                comment(issue, "Codex PR closed without merge; marked `agent:failed`.")
            continue
        if tid in state.review:
            out = gh(
                [
                    "pr",
                    "list",
                    "-R",
                    repo(),
                    "--state",
                    "all",
                    "--search",
                    f"{tid} in:title",
                    "--json",
                    "state,mergedAt",
                ]
            )
            prs = json.loads(out)
            if prs and all(p["state"] == "CLOSED" and not p["mergedAt"] for p in prs):
                set_labels(issue, ["agent:failed"], ["agent:review"])
                comment(issue, "PR closed without merge; marked `agent:failed`.")
    print("reconciled")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--running", default="", help="dry-run only: UC-001:codex,UC-020:claude")
    p.add_argument("--mark", action="store_true", help="label + comment the picked issues")
    p.add_argument("--run-url", default="")
    p.add_argument("--output", choices=["text", "github"], default="text")
    p.add_argument("--cap-total", type=int, default=int(os.environ.get("DISPATCH_CAP", 3)))
    p.add_argument("--cap-claude", type=int, default=int(os.environ.get("DISPATCH_CAP_CLAUDE", 1)))
    p.add_argument("--cap-codex", type=int, default=int(os.environ.get("DISPATCH_CAP_CODEX", 2)))
    p.set_defaults(fn=cmd_plan)
    q = sub.add_parser("prompt")
    q.add_argument("ticket")
    q.add_argument("--agent", choices=AGENT_NAMES, required=True)
    q.add_argument("--issue", type=int)
    q.set_defaults(fn=cmd_prompt)
    f = sub.add_parser("finish")
    f.add_argument("ticket")
    f.add_argument("--agent", choices=AGENT_NAMES, required=True)
    f.add_argument("--result", choices=["success", "failure"], required=True)
    f.add_argument("--pr-url", default="")
    f.add_argument("--run-url", default="")
    f.set_defaults(fn=cmd_finish)
    r = sub.add_parser("reconcile")
    r.set_defaults(fn=cmd_reconcile)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
