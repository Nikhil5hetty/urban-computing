"""UC-060: pure render helpers (every shown number comes from the Answer) + app smoke test."""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

from tests import factories
from urban_computing.assistant.contract import Answer, Explanation, Provenance
from urban_computing.assistant.render import (
    BADGE_HEX,
    answer_view_model,
    chatbot_view_model,
    footer_text,
    truth_badge,
    truth_bar_html,
)
from urban_computing.llm.checkers import CheckResult
from urban_computing.llm.parser import Claim

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "config" / "study.yaml").read_text())


@pytest.mark.parametrize(
    "truth,badge",
    [
        (1.0, "green"),
        (0.6, "green"),
        (0.5999, "amber"),
        (0.3, "amber"),
        (0.2999, "red"),
        (0.0, "red"),
    ],
)
def test_truth_badge_thresholds(truth, badge):
    assert truth_badge(truth) == badge


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def _strings(obj) -> list[str]:
    if isinstance(obj, dict):  # bar_html is styling (CSS sizes / colours), not shown numbers
        return [s for k, v in obj.items() if k != "bar_html" for s in _strings(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in _strings(v)]
    return [obj] if isinstance(obj, str) else []


def test_every_number_shown_comes_from_the_answer():
    ans = factories.sample_answer()
    vm = answer_view_model(ans)
    allowed = _numbers(ans.model_dump_json()) | {f"{e.truth:.2f}" for e in ans.explanations}
    allowed |= {f"{e.coverage:.2f}" for e in ans.explanations if e.coverage is not None}
    allowed |= {f"{ans.question.margin_min:g}"} | {"2026"}  # year of the data period
    shown = set().union(*(_numbers(s) for s in _strings(vm)))
    assert shown <= allowed, shown - allowed
    e = vm["explanations"][0]
    assert (e["truth"], e["badge"], e["bar"], e["coverage"], e["n_text"]) == (
        "0.74",
        "green",
        0.74,
        "0.90",
        "based on 38 observations",
    )


def test_view_model_contents():
    vm = answer_view_model(factories.sample_answer(decision="risky"))
    assert vm["decision"] == {"word": "risky", "label": "Risky", "color": "red"}
    assert vm["official"]["label"] == "Safe"
    assert vm["official"]["sentences"] == ["Most IC1 arrivals at Olten are punctual."]
    assert vm["question"] == "Olten · IC1 → IR16 · morning peak · Mondays · 4 min to change"
    assert vm["fallback_note"] is None and vm["period"] == "2026-10-01..2026-10-28"


def test_footer_from_data_period_and_no_branding():
    ans = factories.sample_answer()
    assert footer_text(ans) == "Data: opentransportdata.swiss (Ist-Daten, Oct 2026)"
    other = ans.model_copy(
        update={"provenance": Provenance(period="2026-09-28..2026-10-04", config_hash="x")}
    )
    assert footer_text(other) == "Data: opentransportdata.swiss (Ist-Daten, Sep 2026 to Oct 2026)"
    for path in [
        ROOT / "src/urban_computing/assistant/render.py",
        *sorted((ROOT / "app").glob("*.py")),
    ]:
        assert "SBB" not in path.read_text(), path  # D-014 / AGENTS §4.8: no SBB branding


def test_measured_share_sentence_has_no_truth_bar():
    count = Explanation(
        sentence="With 4 minutes to change, about 30% of your 40 connections at "
        "Olten were missed or nearly missed (12 clearly missed).",
        quantifier="count",
        summarizer="connection_slack_minutes:missed",
        restriction="own_connections",
        truth=1.0,
        coverage=1.0,
        n=40,
    )
    vm = answer_view_model(factories.sample_answer(explanations=[count]))
    e = vm["explanations"][0]
    assert e["truth"] is None and e["bar"] is None and e["badge"] is None
    assert e["n_text"] == "based on 40 observations"


def test_fallback_note_and_no_official_view():
    ans = factories.sample_answer(
        crisp_decision=None,
        crisp_sentences=[],
        provenance=Provenance(period="2026-10-01..2026-10-28", config_hash="x", fallback=True),
    )
    vm = answer_view_model(ans)
    assert vm["official"] is None and "too few matching connections" in vm["fallback_note"]


def test_chatbot_view_badges():
    def claim(q, s, status="ok", text=""):
        return Claim(question_id="q", slot=0, quantifier=q, summarizer=s, status=status, text=text)

    results = [
        CheckResult(
            claim=claim("most", "arrival_delay_minutes:on_time", text="Most are on time."),
            crisp=True,
            fuzzy=0.91,
            fuzzy_true=True,
            disagreement="none",
        ),
        CheckResult(
            claim=claim("most", "arrival_delay_minutes:late"),
            crisp=True,
            fuzzy=0.057,
            fuzzy_true=False,
            disagreement="crisp_true_fuzzy_false",
        ),
        CheckResult(
            claim=claim(None, None, status="unverifiable_causal", text="Due to works."),
            crisp=None,
            fuzzy=None,
            fuzzy_true=None,
            disagreement="n/a",
            reason="status unverifiable_causal",
        ),
    ]
    vm = chatbot_view_model("Most trains are on time.", results)
    assert vm["text"] == "Most trains are on time."
    assert [(c["truth"], c["badge"]) for c in vm["claims"]] == [
        ("0.91", "green"),
        ("0.06", "red"),
        (None, "gray"),
    ]
    assert vm["claims"][1]["text"] == "most arrival_delay_minutes:late"
    assert "unverifiable_causal" in vm["claims"][2]["note"]


def test_answer_view_model_reads_only_the_answer():
    src = (ROOT / "src/urban_computing/assistant/render.py").read_text()
    imports = {
        (n.module or "").split(".")[0] if isinstance(n, ast.ImportFrom) else a.name
        for n in ast.walk(ast.parse(src))
        if isinstance(n, (ast.Import, ast.ImportFrom))
        for a in (n.names if isinstance(n, ast.Import) else [None])
    }
    assert not imports & {"streamlit", "pandas", "duckdb", "yaml", "pathlib", "os"}


# --------------------------------------------------------------------- app (glue smoke test)


def test_app_never_imports_llm_runtimes():
    for path in sorted((ROOT / "app").glob("*.py")):
        tree = ast.parse(path.read_text())
        mods = {
            (n.module or "") if isinstance(n, ast.ImportFrom) else a.name
            for n in ast.walk(tree)
            if isinstance(n, (ast.Import, ast.ImportFrom))
            for a in (n.names if isinstance(n, ast.Import) else [None])
        }
        bad = {
            m
            for m in mods
            if m and m.split(".")[0] in {"transformers", "torch", "vllm", "openai", "anthropic"}
        }
        assert not bad and "urban_computing.llm.runner" not in mods, (path, bad)


@pytest.mark.parametrize("view", ["answer", "official", "chatbot"])
def test_app_runs_on_the_fixture(monkeypatch, view):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(sys, "argv", ["main.py", "--sample"])
    at = AppTest.from_file(str(ROOT / "app" / "main.py"), default_timeout=180)
    at.query_params.update(
        {
            "hub": "Zürich HB",
            "arr_line": "IC1",
            "time_band": "morning_peak",
            "day": "all",
            "margin": "3",
            "view": view,
        }
    )
    at.run()
    assert not at.exception
    captions = [c.value for c in at.caption]
    assert "Data: opentransportdata.swiss (Ist-Daten, Oct 2026)" in captions
    hubs = at.sidebar.selectbox[0].options
    assert hubs == CONFIG["connections"]["hubs"]  # exact config names (PM review of #38)
    assert at.sidebar.selectbox[3].options == [b.replace("_", " ") for b in CONFIG["time_bands"]]
    md = " ".join(m.value for m in at.markdown)
    if view == "answer":
        assert "about half of your connections at Zürich HB are missed" in md
        assert BADGE_HEX["green"] in md  # truth 1.00 -> green bar, not the theme's red
    elif view == "official":
        assert "13 of 25 arrivals were 3 or more minutes late." in md
        assert "about half of your connections at Zürich HB are missed" in md  # side by side
    else:
        assert "No cached chatbot answer" in md


def test_answer_json_round_trip_keeps_view_model():
    ans = factories.sample_answer()
    again = Answer.model_validate(json.loads(ans.model_dump_json()))
    assert answer_view_model(again) == answer_view_model(ans)


# --------------------------------------------------------------------- review #58


@pytest.mark.parametrize("truth,badge", [(1.0, "green"), (0.45, "amber"), (0.1, "red")])
def test_truth_bar_colour_follows_the_badge(truth, badge):
    ex = factories.sample_answer().explanations[0].model_copy(update={"truth": truth})
    vm = answer_view_model(factories.sample_answer(decision="risky", explanations=[ex]))
    e = vm["explanations"][0]
    assert e["badge"] == badge
    assert e["bar_html"] == truth_bar_html(truth, badge)
    assert BADGE_HEX[badge] in e["bar_html"]
    others = {c for b, c in BADGE_HEX.items() if b != badge}
    assert not any(c in e["bar_html"] for c in others)
    assert f"width:{round(100 * truth, 1)}%" in e["bar_html"]


def test_fully_true_sentence_is_green_even_when_the_decision_is_risky():
    vm = answer_view_model(factories.sample_answer(decision="risky"))
    assert vm["decision"]["color"] == "red"
    ex = factories.sample_answer().explanations[0].model_copy(update={"truth": 1.0})
    vm = answer_view_model(factories.sample_answer(decision="risky", explanations=[ex]))
    assert BADGE_HEX["green"] in vm["explanations"][0]["bar_html"]


def test_own_sentences_for_the_official_side_by_side():
    own = Explanation(sentence="With 4 minutes to change, few of your connections at Olten are "
                      "missed.", quantifier="few", summarizer="connection_slack_minutes:missed",
                      restriction="own_connections", truth=1.0, coverage=1.0, n=30)  # fmt: skip
    mined = factories.sample_answer().explanations[0]  # restriction hub=Olten&...
    vm = answer_view_model(factories.sample_answer(explanations=[own, mined]))
    assert vm["own_sentences"] == [own.sentence]
    fallback = own.model_copy(update={"restriction": "own_arrivals", "sentence": "x"})
    assert answer_view_model(factories.sample_answer(explanations=[fallback]))["own_sentences"] == [
        "x"
    ]
