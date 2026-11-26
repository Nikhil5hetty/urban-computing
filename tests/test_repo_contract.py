"""Repository contract: the planning files agents rely on stay valid.

These tests guard the project-management layer (tickets, pre-registration, config), not the
science code. They run offline and need only PyYAML.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load_tickets_module():
    spec = importlib.util.spec_from_file_location("tickets", ROOT / "scripts" / "tickets.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tickets"] = mod  # dataclasses need the module registered
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


T = _load_tickets_module()


def test_tickets_are_valid():
    tickets = T.load_all()
    assert len(tickets) >= 30
    assert T.validate(tickets) == []


def test_ticket_touches_are_inside_repo():
    for t in T.load_all():
        for p in t.meta["touches"]:
            assert not p.startswith("/") and ".." not in p, f"{t.id}: bad path {p}"
            assert not p.startswith("data/raw"), f"{t.id}: may not touch data/raw"


def test_every_hypothesis_and_invariant_has_a_ticket():
    hyp = yaml.safe_load((ROOT / "eval" / "hypotheses.yaml").read_text())
    ids = {t.id for t in T.load_all()}
    for h in hyp["hypotheses"] + hyp["invariants"]:
        assert h["ticket"] in ids, f"{h['id']} points to unknown ticket {h['ticket']}"


def test_hypotheses_schema():
    hyp = yaml.safe_load((ROOT / "eval" / "hypotheses.yaml").read_text())
    seen = set()
    for h in hyp["hypotheses"]:
        for key in ("id", "rq", "statement", "metric", "test", "supported_if", "not_supported_if"):
            assert key in h, f"{h.get('id')}: missing {key}"
        assert re.fullmatch(r"H[1-3][a-z]", h["id"])
        assert h["rq"] in {"SRQ1", "SRQ2", "SRQ3"}
        assert h["id"] not in seen
        seen.add(h["id"])
    assert {i["id"] for i in hyp["invariants"]} == {f"I{n}" for n in range(1, 7)}


def test_vocabulary_trapezoids_are_ordered():
    vocab = yaml.safe_load((ROOT / "config" / "vocabulary.yaml").read_text())
    groups = list(vocab["summarizers"].values()) + list(vocab["quantifiers"].values())
    for group in groups:
        for word, abcd in group.items():
            assert len(abcd) == 4, word
            finite = [x for x in abcd if x is not None]
            assert finite == sorted(finite), f"{word}: breakpoints not ordered {abcd}"


def test_quantifiers_live_in_unit_interval():
    vocab = yaml.safe_load((ROOT / "config" / "vocabulary.yaml").read_text())
    for group in vocab["quantifiers"].values():
        for word, abcd in group.items():
            assert all(x is None or 0 <= x <= 1 for x in abcd), word


def test_study_config_loads_and_is_consistent():
    cfg = yaml.safe_load((ROOT / "config" / "study.yaml").read_text())
    assert cfg["data"]["keep_status"] == ["REAL"]
    assert cfg["crisp_baseline"]["punctual_threshold_minutes"] == 3
    assert cfg["mining"]["beta"] == 0.6
    assert len(cfg["connections"]["hubs"]) == 3


def test_agent_brief_exists_and_is_imported_by_claude_md():
    assert (ROOT / "AGENTS.md").exists()
    assert (ROOT / "CLAUDE.md").read_text().startswith("@AGENTS.md")
