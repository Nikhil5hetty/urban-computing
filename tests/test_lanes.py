"""Agent lanes (D-020): Claude and Codex tickets never touch the same path.

Claude (cloud dispatcher) and Codex (local runner) work in parallel. If a file belongs to
tickets of both agents, their PRs can conflict, so every agent ticket has a fixed agent
and the two lanes' `touches:` paths are disjoint. Tickets of the same agent may share a
path: each agent works one ticket at a time.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("tickets", ROOT / "scripts" / "tickets.py")
tk = importlib.util.module_from_spec(_spec)
sys.modules["tickets"] = tk
assert _spec.loader is not None
_spec.loader.exec_module(tk)

AGENT_TICKETS = [t for t in tk.load_all() if t.meta.get("owner") == "agent"]


def _overlap(a: str, b: str) -> bool:
    """Same file, or one path is a directory containing the other."""
    a, b = a.rstrip("/"), b.rstrip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def test_every_agent_ticket_has_a_fixed_agent():
    loose = [t.id for t in AGENT_TICKETS if t.meta.get("agent") not in ("claude", "codex")]
    assert not loose, f"assign claude or codex (no `any`) to: {loose}"


def test_claude_and_codex_lanes_touch_disjoint_paths():
    lanes = {
        a: [(t.id, p) for t in AGENT_TICKETS if t.meta["agent"] == a for p in t.meta["touches"]]
        for a in ("claude", "codex")
    }
    clashes = [
        f"{ca} {cp}  <->  {xa} {xp}"
        for ca, cp in lanes["claude"]
        for xa, xp in lanes["codex"]
        if _overlap(cp, xp)
    ]
    assert not clashes, "shared paths between lanes:\n" + "\n".join(clashes)
