#!/usr/bin/env python3
"""Ticket utilities: validate specs, list ready tickets, show the dependency graph.

Usage:
    python3 scripts/tickets.py validate
    python3 scripts/tickets.py ready [--strict]   # strict = also wait for soft deps
    python3 scripts/tickets.py graph
    python3 scripts/tickets.py set-status UC-021 in-progress

Tickets live in tickets/UC-xxx-*.md with YAML frontmatter (see tickets/README.md).
Only depends on PyYAML so it runs before `uv sync`.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TICKET_DIR = ROOT / "tickets"

EPICS = {
    "setup",
    "research",
    "data",
    "fuzzy",
    "assistant",
    "llm",
    "evaluation",
    "prototype",
    "paper",
}
MILESTONES = {
    "M1": ("M1 Data + fuzzy core", "2026-11-29"),
    "M2": ("M2 Assistant + SRQ1/2", "2026-12-02"),
    "M3": ("M3 LLM audit + prototype", "2026-12-04"),
    "M4": ("M4 Paper + submission", "2026-12-06"),
}
STATUSES = {"todo", "in-progress", "blocked", "done"}
OWNERS = {"agent", "nikhil", "pm"}
AGENTS = {"claude", "codex", "any", "none"}
REQUIRED = {
    "id": str,
    "title": str,
    "epic": str,
    "milestone": str,
    "status": str,
    "owner": str,
    "estimate_h": (int, float),
    "depends_on": list,
    "soft_depends_on": list,
    "agent": str,
    "touches": list,
    "realdata": bool,
}
REQUIRED_SECTIONS = ["## Goal", "## Acceptance criteria"]
ID_RE = re.compile(r"^UC-\d{3}$")


@dataclass
class Ticket:
    path: Path
    meta: dict
    body: str
    errors: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return str(self.meta.get("id", ""))


def parse(path: Path) -> Ticket:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return Ticket(path, {}, text, [f"{path.name}: missing frontmatter"])
    try:
        _, fm, body = text.split("---\n", 2)
    except ValueError:
        return Ticket(path, {}, text, [f"{path.name}: unterminated frontmatter"])
    meta = yaml.safe_load(fm) or {}
    return Ticket(path, meta, body.strip())


def load_all(ticket_dir: Path = TICKET_DIR) -> list[Ticket]:
    return [parse(p) for p in sorted(ticket_dir.glob("UC-*.md"))]


def _find_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    color: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        color[node] = 1
        stack.append(node)
        for dep in graph.get(node, []):
            if color.get(dep) == 1:
                return stack[stack.index(dep) :] + [dep]
            if color.get(dep, 0) == 0:
                found = visit(dep)
                if found:
                    return found
        stack.pop()
        color[node] = 2
        return None

    for n in graph:
        if color.get(n, 0) == 0:
            found = visit(n)
            if found:
                return found
    return None


def validate(tickets: list[Ticket]) -> list[str]:
    errors: list[str] = []
    ids: dict[str, Path] = {}
    for t in tickets:
        errors.extend(t.errors)
        m = t.meta
        for key, typ in REQUIRED.items():
            if key not in m:
                errors.append(f"{t.path.name}: missing '{key}'")
            elif not isinstance(m[key], typ):
                errors.append(f"{t.path.name}: '{key}' has wrong type")
        if not m:
            continue
        if not ID_RE.match(t.id):
            errors.append(f"{t.path.name}: bad id '{t.id}'")
        if not t.path.name.startswith(t.id + "-"):
            errors.append(f"{t.path.name}: filename must start with '{t.id}-'")
        if t.id in ids:
            errors.append(f"{t.path.name}: duplicate id {t.id} (also {ids[t.id].name})")
        ids[t.id] = t.path
        if m.get("epic") not in EPICS:
            errors.append(f"{t.path.name}: unknown epic '{m.get('epic')}'")
        if m.get("milestone") not in MILESTONES:
            errors.append(f"{t.path.name}: unknown milestone '{m.get('milestone')}'")
        if m.get("status") not in STATUSES:
            errors.append(f"{t.path.name}: unknown status '{m.get('status')}'")
        if m.get("owner") not in OWNERS:
            errors.append(f"{t.path.name}: unknown owner '{m.get('owner')}'")
        if m.get("agent") not in AGENTS:
            errors.append(f"{t.path.name}: unknown agent '{m.get('agent')}'")
        elif (m.get("owner") == "agent") != (m.get("agent") != "none"):
            errors.append(f"{t.path.name}: agent must be 'none' iff owner is not 'agent'")
        hard, soft = set(m.get("depends_on") or []), set(m.get("soft_depends_on") or [])
        if hard & soft:
            errors.append(f"{t.path.name}: {sorted(hard & soft)} both hard and soft")
        for sec in REQUIRED_SECTIONS:
            if sec not in t.body:
                errors.append(f"{t.path.name}: missing section '{sec}'")
        if "- [ ]" not in t.body and "- [x]" not in t.body:
            errors.append(f"{t.path.name}: acceptance criteria need checkboxes")
    graph = {t.id: list(t.meta.get("depends_on") or []) for t in tickets if t.meta}
    for tid, deps in graph.items():
        for d in deps:
            if d not in graph:
                errors.append(f"{tid}: depends on unknown ticket {d}")
            if d == tid:
                errors.append(f"{tid}: depends on itself")
    order = list(MILESTONES)
    by_id = {t.id: t for t in tickets if t.meta}
    for tid, deps in graph.items():
        for d in deps:
            if d in by_id and tid in by_id:
                m_self = order.index(by_id[tid].meta.get("milestone", "M4"))
                m_dep = order.index(by_id[d].meta.get("milestone", "M1"))
                if m_dep > m_self:
                    errors.append(f"{tid}: depends on {d} from a later milestone")
    for t in tickets:
        for d in t.meta.get("soft_depends_on") or []:
            if d not in graph:
                errors.append(f"{t.id}: soft-depends on unknown ticket {d}")
            if d == t.id:
                errors.append(f"{t.id}: soft-depends on itself")
    cycle = _find_cycle(graph)
    if cycle:
        errors.append("dependency cycle: " + " -> ".join(cycle))
    return errors


def ready(tickets: list[Ticket], strict: bool = False) -> list[Ticket]:
    """`todo` tickets whose HARD dependencies are all `done` (soft too if strict)."""
    status = {t.id: t.meta.get("status") for t in tickets}
    out = []
    for t in tickets:
        if t.meta.get("status") != "todo":
            continue
        deps = list(t.meta.get("depends_on") or [])
        if strict:
            deps += list(t.meta.get("soft_depends_on") or [])
        if all(status.get(d) == "done" for d in deps):
            out.append(t)
    return out


def done_ids(tickets: list[Ticket]) -> set[str]:
    return {t.id for t in tickets if t.meta.get("status") == "done"}


def set_status(tickets: list[Ticket], tid: str, new: str) -> Path:
    if new not in STATUSES:
        raise SystemExit(f"status must be one of {sorted(STATUSES)}")
    for t in tickets:
        if t.id == tid:
            text = t.path.read_text(encoding="utf-8")
            text = re.sub(r"(?m)^status: .*$", f"status: {new}", text, count=1)
            t.path.write_text(text, encoding="utf-8")
            return t.path
    raise SystemExit(f"unknown ticket {tid}")


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "validate"
    tickets = load_all()
    if cmd == "validate":
        errs = validate(tickets)
        for e in errs:
            print("ERROR", e)
        print(f"{len(tickets)} tickets, {len(errs)} errors")
        return 1 if errs else 0
    if cmd == "ready":
        strict = "--strict" in argv
        for t in ready(tickets, strict=strict):
            m = t.meta
            soft = [d for d in m.get("soft_depends_on") or [] if d not in done_ids(tickets)]
            note = f"  (soft pending: {', '.join(soft)})" if soft else ""
            tag = f"[{m['milestone']}/{m['epic']}/{m['owner']}:{m['agent']}]"
            print(f"{t.id}  {tag}  {m['title']}{note}")
        return 0
    if cmd == "graph":
        for ms, (title, due) in MILESTONES.items():
            print(f"\n{title} (due {due})")
            for t in tickets:
                if t.meta.get("milestone") == ms:
                    deps = ", ".join(t.meta.get("depends_on") or []) or "-"
                    soft = ", ".join(t.meta.get("soft_depends_on") or [])
                    soft = f"  ~ {soft}" if soft else ""
                    print(f"  {t.id} [{t.meta['status']}] {t.meta['title']}  <- {deps}{soft}")
        return 0
    if cmd == "set-status" and len(argv) == 4:
        print(set_status(tickets, argv[2], argv[3]))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
