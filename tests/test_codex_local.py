"""Local Codex runner helpers (offline; no git, gh or codex calls)."""

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
cl = _load("codex_local")


def test_outside_touches_prefix_exact_glob_and_ticket_files():
    touches = ["src/urban_computing/fuzzy/", "docs/methods.md", "tests/test_fuzzy_*.py"]
    files = [
        "src/urban_computing/fuzzy/truth.py",
        "docs/methods.md",
        "tests/test_fuzzy_truth.py",
        "tickets/UC-021-truth-engine.md",
        "docs/data.md",
        "src/urban_computing/fuzzyx.py",
    ]
    assert cl.outside_touches(files, touches) == ["docs/data.md", "src/urban_computing/fuzzyx.py"]


def test_uv_lock_only_staged_when_ticket_touches_it():
    assert ":(exclude)uv.lock" in cl.stage_pathspec(["src/"])
    assert ":(exclude)uv.lock" not in cl.stage_pathspec(["pyproject.toml", "uv.lock"])


def test_pr_body_adds_closes_and_warnings():
    body = cl.pr_body("Did things.", 7, ["outside `touches:`: `x`"])
    assert "Closes #7" in body and "Runner warnings" in body
    assert cl.pr_body("Closes #7", 7, []).count("#7") == 1


def test_local_prompt_forbids_git_and_names_branch():
    t = next(t for t in tk.load_all() if t.meta.get("agent") == "codex")
    text = dispatch.render_prompt(t, "codex", 4, variant="codex_local")
    assert "Do NOT run `git commit`" in text
    assert dispatch.branch_for(t) in text and "Closes #4" in text
    assert "Codex cloud task" not in text
    # default variant unchanged
    assert "Codex cloud task" in dispatch.render_prompt(t, "codex", 4)
