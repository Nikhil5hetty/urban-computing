"""Dispatcher selection logic (offline)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


tk = _load("tickets")
dispatch = _load("dispatch")


def _setup():
    """All tickets as at the project start (status todo), so the selection tests do not
    depend on how far the live board has progressed (they failed once few tickets were
    left; UC-061 CI)."""
    tickets = tk.load_all()
    for t in tickets:
        t.meta["status"] = "todo"
    issue_map = {t.id: {"number": i + 1} for i, t in enumerate(tickets)}
    return tickets, issue_map


def test_initial_wave_respects_caps_and_skips_humans():
    tickets, issue_map = _setup()
    state = dispatch.State(running={}, review=set(), failed=set())
    picks = dispatch.select(
        tickets, state, issue_map, cap_total=4, cap_agent={"claude": 2, "codex": 2}
    )
    assert len(picks) == 4
    assert sum(p.agent == "claude" for p in picks) == 2
    assert sum(p.agent == "codex" for p in picks) == 2
    owners = {t.id: t.meta["owner"] for t in tickets}
    assert all(owners[p.id] == "agent" for p in picks)


def test_setup_first_then_critical_path():
    tickets, issue_map = _setup()
    # Exercise the initial setup wave regardless of the live status of these tickets.
    for ticket in tickets:
        if ticket.id in {"UC-001", "UC-004"}:
            ticket.meta["status"] = "todo"
    state = dispatch.State(running={}, review=set(), failed=set())
    picks = dispatch.select(
        tickets, state, issue_map, cap_total=4, cap_agent={"claude": 2, "codex": 2}
    )
    ids = [p.id for p in picks]
    assert "UC-001" in ids and "UC-004" in ids  # setup epic first (both codex)
    counts = dispatch.unblock_counts(tickets)
    claude_ready = [
        t.id
        for t in tk.ready(tickets)
        if t.meta["owner"] == "agent" and t.meta["agent"] == "claude"
    ]
    first_claude = next(p.id for p in picks if p.agent == "claude")
    assert counts[first_claude] == max(counts[i] for i in claude_ready)


def test_running_review_failed_are_not_redispatched_and_count_correctly():
    tickets, issue_map = _setup()
    first = dispatch.select(
        tickets, dispatch.State({}, set(), set()), issue_map, 10, {"claude": 5, "codex": 5}
    )
    ids = [p.id for p in first]
    state = dispatch.State(running={ids[0]: first[0].agent}, review={ids[1]}, failed={ids[2]})
    again = dispatch.select(tickets, state, issue_map, 10, {"claude": 5, "codex": 5})
    assert not {ids[0], ids[1], ids[2]} & {p.id for p in again}


def test_full_caps_start_nothing():
    tickets, issue_map = _setup()
    state = dispatch.State(
        running={"UC-001": "codex", "UC-020": "claude"}, review=set(), failed=set()
    )
    assert dispatch.select(tickets, state, issue_map, cap_total=2) == []


def test_tickets_without_issue_are_skipped():
    tickets, _ = _setup()
    state = dispatch.State({}, set(), set())
    assert dispatch.select(tickets, state, {}, cap_total=4) == []


def test_prompt_mentions_ticket_and_rules():
    t = next(t for t in tk.load_all() if t.id == "UC-021")
    for agent in ("claude", "codex"):
        text = dispatch.render_prompt(t, agent, 12)
        assert "UC-021" in text and "#12" in text and "AGENTS.md" in text
        assert t.path.name in text
    assert "Codex cloud task" in dispatch.render_prompt(t, "codex", 12)
    assert "gh pr create" in dispatch.render_prompt(t, "claude", 12)
