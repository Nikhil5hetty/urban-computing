#!/usr/bin/env python3
"""Create the GitHub board from tickets/: labels, milestones, issues, Project (v2).

Idempotent: tickets already in tickets/ISSUE_MAP.json are updated, not duplicated.

Prerequisites (run once):
    gh auth login
    gh auth refresh -s project          # Projects v2 needs the 'project' scope

Usage:
    python3 scripts/bootstrap_github.py --dry-run
    python3 scripts/bootstrap_github.py --repo Nikhil5hetty/urban-computing
    python3 scripts/bootstrap_github.py --repo OWNER/REPO --sync-status   # re-sync later

What it does:
    1. labels  epic:<epic>, owner:<owner>, realdata, blocked
    2. milestones M1..M4 with due dates (23:59 Europe/Zurich)
    3. one issue per ticket: title "UC-xxx: <title>", body = ticket spec with
       dependencies rewritten as issue links; closed if status is done
    4. a Project named "urban-computing" with every issue added and Status set
       (Todo / In Progress / Done; blocked tickets stay Todo with label 'blocked')
    5. writes tickets/ISSUE_MAP.json  {"UC-001": {"number": 1, "url": "..."}}
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tickets as tk  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "tickets" / "ISSUE_MAP.json"
PROJECT_TITLE = "urban-computing"

EPIC_COLORS = {
    "setup": "6e7781",
    "research": "8250df",
    "data": "0969da",
    "fuzzy": "1a7f37",
    "assistant": "bf3989",
    "llm": "cf222e",
    "evaluation": "9a6700",
    "prototype": "0550ae",
    "paper": "57606a",
}
STATUS_TO_BOARD = {"todo": "Todo", "blocked": "Todo", "in-progress": "In Progress", "done": "Done"}


class GH:
    def __init__(self, repo: str, dry_run: bool):
        self.repo = repo
        self.dry = dry_run
        self.owner = repo.split("/")[0]

    def run(self, args: list[str], capture: bool = True) -> str:
        cmd = ["gh", *args]
        if self.dry:
            print("DRY", " ".join(_q(a) for a in cmd))
            return ""
        res = subprocess.run(cmd, capture_output=capture, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"{' '.join(cmd)}\n{res.stderr}")
        return res.stdout.strip()


def _q(a: str) -> str:
    return f"'{a}'" if (" " in a or not a) else a


def issue_body(t: tk.Ticket, issue_map: dict) -> str:
    deps = t.meta.get("depends_on") or []
    dep_links = [f"#{issue_map[d]['number']} ({d})" if d in issue_map else d for d in deps] or [
        "none"
    ]
    touches = "\n".join(f"- `{p}`" for p in t.meta.get("touches") or [])
    return (
        f"> Spec and status source of truth: `tickets/{t.path.name}` "
        f"(edit the file, not this issue).\n\n"
        f"**Milestone:** {t.meta['milestone']} · **Epic:** {t.meta['epic']} · "
        f"**Owner:** {t.meta['owner']} · **Estimate:** {t.meta['estimate_h']} h · "
        f"**Needs real data:** {t.meta['realdata']}\n\n"
        f"**Depends on:** {', '.join(dep_links)}\n\n"
        f"**May touch:**\n{touches}\n\n---\n\n{t.body}\n\n---\n"
        f"Read `AGENTS.md` first. Definition of Done: `docs/evaluation.md` §1.\n"
    )


def ensure_labels(gh: GH) -> None:
    for epic, color in EPIC_COLORS.items():
        gh.run(["label", "create", f"epic:{epic}", "--color", color, "--force", "-R", gh.repo])
    for owner in sorted(tk.OWNERS):
        gh.run(["label", "create", f"owner:{owner}", "--color", "c5def5", "--force", "-R", gh.repo])
    gh.run(["label", "create", "realdata", "--color", "fbca04", "--force", "-R", gh.repo])
    gh.run(["label", "create", "blocked", "--color", "b60205", "--force", "-R", gh.repo])


def ensure_milestones(gh: GH) -> None:
    existing = set()
    if not gh.dry:
        out = gh.run(["api", f"repos/{gh.repo}/milestones?state=all", "--jq", ".[].title"])
        existing = set(out.splitlines())
    for title, due in tk.MILESTONES.values():
        if title in existing:
            continue
        gh.run(
            [
                "api",
                f"repos/{gh.repo}/milestones",
                "-f",
                f"title={title}",
                "-f",
                f"due_on={due}T22:59:59Z",
            ]
        )


def labels_for(t: tk.Ticket) -> list[str]:
    labels = [f"epic:{t.meta['epic']}", f"owner:{t.meta['owner']}"]
    if t.meta.get("realdata"):
        labels.append("realdata")
    if t.meta.get("status") == "blocked":
        labels.append("blocked")
    return labels


def upsert_issues(gh: GH, tickets: list[tk.Ticket], issue_map: dict) -> None:
    # Pass 1: create missing issues so every ticket has a number.
    for t in tickets:
        if t.id in issue_map:
            continue
        title = f"{t.id}: {t.meta['title']}"
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
            fh.write(issue_body(t, issue_map))
        args = ["issue", "create", "-R", gh.repo, "--title", title, "--body-file", fh.name]
        args += ["--milestone", tk.MILESTONES[t.meta["milestone"]][0]]
        for lab in labels_for(t):
            args += ["--label", lab]
        url = gh.run(args)
        if gh.dry:
            issue_map[t.id] = {"number": 0, "url": f"<{t.id}>"}
        else:
            issue_map[t.id] = {"number": int(url.rstrip("/").split("/")[-1]), "url": url}
    # Pass 2: rewrite bodies (dependency links now resolvable), labels, open/closed state.
    for t in tickets:
        num = str(issue_map[t.id]["number"])
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
            fh.write(issue_body(t, issue_map))
        args = ["issue", "edit", num, "-R", gh.repo, "--body-file", fh.name]
        for lab in labels_for(t):
            args += ["--add-label", lab]
        if t.meta.get("status") != "blocked":
            args += ["--remove-label", "blocked"]
        gh.run(args)
        if t.meta.get("status") == "done":
            gh.run(["issue", "close", num, "-R", gh.repo, "--reason", "completed"])


def ensure_project(gh: GH) -> str:
    if gh.dry:
        gh.run(["project", "create", "--owner", gh.owner, "--title", PROJECT_TITLE])
        return "<project-number>"
    out = gh.run(["project", "list", "--owner", gh.owner, "--format", "json", "--limit", "100"])
    for p in json.loads(out).get("projects", []):
        if p.get("title") == PROJECT_TITLE:
            return str(p["number"])
    out = gh.run(
        ["project", "create", "--owner", gh.owner, "--title", PROJECT_TITLE, "--format", "json"]
    )
    number = str(json.loads(out)["number"])
    gh.run(["project", "link", number, "--owner", gh.owner, "--repo", gh.repo])
    return number


def add_and_set_status(gh: GH, number: str, tickets: list[tk.Ticket], issue_map: dict) -> None:
    project_id = status_field = None
    options: dict[str, str] = {}
    if not gh.dry:
        view = json.loads(
            gh.run(["project", "view", number, "--owner", gh.owner, "--format", "json"])
        )
        project_id = view["id"]
        fields = json.loads(
            gh.run(["project", "field-list", number, "--owner", gh.owner, "--format", "json"])
        )
        for f in fields.get("fields", []):
            if f.get("name") == "Status":
                status_field = f["id"]
                options = {o["name"]: o["id"] for o in f.get("options", [])}
    for t in tickets:
        url = issue_map[t.id]["url"]
        out = gh.run(
            ["project", "item-add", number, "--owner", gh.owner, "--url", url, "--format", "json"]
        )
        if gh.dry or not status_field:
            continue
        item_id = json.loads(out)["id"]
        opt = options.get(STATUS_TO_BOARD[t.meta["status"]])
        if opt:
            gh.run(
                [
                    "project",
                    "item-edit",
                    "--id",
                    item_id,
                    "--project-id",
                    project_id,
                    "--field-id",
                    status_field,
                    "--single-select-option-id",
                    opt,
                ]
            )


def detect_repo() -> str:
    res = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if res.returncode != 0 or not res.stdout.strip():
        raise SystemExit("Could not detect repo; pass --repo OWNER/REPO")
    return res.stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--repo", help="OWNER/REPO (default: detect from git remote)")
    ap.add_argument("--dry-run", action="store_true", help="print gh commands only")
    ap.add_argument("--sync-status", action="store_true", help="only re-sync issues + board")
    args = ap.parse_args()

    tickets = tk.load_all()
    errs = tk.validate(tickets)
    if errs:
        for e in errs:
            print("ERROR", e)
        return 1
    repo = args.repo or ("OWNER/urban-computing" if args.dry_run else detect_repo())
    gh = GH(repo, args.dry_run)
    issue_map = json.loads(MAP_PATH.read_text()) if MAP_PATH.exists() else {}

    if not args.sync_status:
        ensure_labels(gh)
        ensure_milestones(gh)
    upsert_issues(gh, tickets, issue_map)
    number = ensure_project(gh)
    add_and_set_status(gh, number, tickets, issue_map)

    if not args.dry_run:
        MAP_PATH.write_text(json.dumps(issue_map, indent=2, sort_keys=True) + "\n")
        print(f"Wrote {MAP_PATH.relative_to(ROOT)}; commit it.")
    print(f"Done: {len(tickets)} tickets -> {repo}, project '{PROJECT_TITLE}' #{number}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
