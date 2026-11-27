"""UC-054: ablations run from config / vocabulary overrides and flag verdict changes."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

from urban_computing.evaluation import ablations, registry
from urban_computing.evaluation.registry import Context, Result
from urban_computing.fuzzy.vocabulary import load_vocabulary, vocabulary_from_dict
from urban_computing.llm.checkers import crisp_intervals

ROOT = Path(__file__).resolve().parents[1]
VOCAB = ROOT / "config/vocabulary.yaml"


def _config():
    return yaml.safe_load((ROOT / "config/study.yaml").read_text(encoding="utf-8"))


def _vocab_dict():
    return yaml.safe_load(VOCAB.read_text(encoding="utf-8"))


def test_merge_is_deep_and_does_not_touch_the_base():
    base = {"mining": {"beta": 0.6, "tnorm": "product"}, "llm": {"seeds": [1]}}
    merged = ablations.merge(base, {"mining": {"tnorm": "min"}})
    assert merged == {"mining": {"beta": 0.6, "tnorm": "min"}, "llm": {"seeds": [1]}}
    assert base["mining"]["tnorm"] == "product"


def test_settings_cover_the_ticket_and_skip_the_defaults():
    found = {(a.name, a.setting) for a in ablations.ablations(_config())}
    assert {("tnorm", "min"), ("beta", "0.5"), ("beta", "0.7")} <= found
    assert ("beta", "0.6") not in found  # the pre-registered value is the baseline
    assert {("coverage_r2", "0.1"), ("coverage_r2", "0.2")} <= found
    assert ("coverage_r2", "0.15") not in found
    assert {("delay_breakpoints", "-1"), ("delay_breakpoints", "+1")} <= found
    assert ("quantifiers", "core+extended") in found
    assert {("min_transfer", "1"), ("min_transfer", "3"), ("min_transfer", "4")} <= found
    assert ("min_transfer", "2") not in found
    assert ("crisp_late", "official_ge_3") in found
    assert {("llm_temperature", "0"), ("llm_temperature", "0.7")} <= found
    tnorm = next(a for a in ablations.ablations(_config()) if a.name == "tnorm")
    assert "qc_tnorm" not in tnorm.overrides["mining"]  # Q_c stays on the product (D-027)


def test_vocabulary_edits_stay_valid():
    shifted = vocabulary_from_dict(ablations.shift_delay_breakpoints(1)(_vocab_dict()))
    base = load_vocabulary(VOCAB)
    for word, t in base.summarizers["arrival_delay_minutes"].items():
        s = shifted.summarizers["arrival_delay_minutes"][word]
        assert [None if v is None else v - 1 for v in (s.a, s.b, s.c, s.d)] == [t.a, t.b, t.c, t.d]
    extended = vocabulary_from_dict(ablations.with_extended_quantifiers(_vocab_dict()))
    assert set(extended.quantifiers["core"]) == {
        "few", "about_half", "most", "almost_none", "almost_all"
    }  # fmt: skip


def test_official_late_switch_changes_only_the_crisp_late_interval():
    vocab = load_vocabulary(VOCAB)
    config = _config()
    default = crisp_intervals(vocab, config)["arrival_delay_minutes"]
    official = crisp_intervals(
        vocab, ablations.merge(config, {"crisp_baseline": {"official_late": 1}})
    )["arrival_delay_minutes"]
    assert default["late"] == (4.0, 9.0)  # crossovers of the fuzzy partition (D-023)
    assert official["late"] == (3.0, np.inf)  # official: late = not punctual (D-007)
    assert {w: v for w, v in official.items() if w != "late"} == {
        w: v for w, v in default.items() if w != "late"
    }


@pytest.fixture
def fake_experiments(monkeypatch):
    """Experiments whose metric shows which override reached them."""

    def h1a(ctx):
        beta = ctx.config["mining"]["beta"]
        return Result(point=0.5 if beta == 0.6 else 0.0, ci_low=0.3, ci_high=0.7)

    def h2a(ctx):
        minutes = ctx.config["connections"]["min_transfer_minutes_default"]
        return Result(point=0.2 if minutes <= 2 else 0.01, ci_low=0.1, ci_high=0.3)

    def h3c(ctx):
        vocab = load_vocabulary(Path(ctx.paths["vocabulary"]))
        on_time_c = vocab.summarizers["arrival_delay_minutes"]["on_time"].c
        official = ctx.config["crisp_baseline"].get("official_late", 0)
        return Result(point=on_time_c + official, ci_low=0.1)  # base: c = 1, no official

    experiments = {"H1a": h1a, "H2a": h2a, "H3c": h3c}
    monkeypatch.setattr(registry, "EXPERIMENTS", experiments)
    monkeypatch.setattr(ablations, "_i4_tables", lambda ctx: ("arrivals", "connections", None))
    monkeypatch.setattr(ablations, "_temperature_runs", lambda base, t: "runs")
    return Context(_config(), True, {"vocabulary": str(VOCAB)}, 1)


def test_overrides_reach_the_experiments_and_flag_verdict_changes(fake_experiments):
    rows = ablations.ablation_table(fake_experiments).rows
    by = {(r["ablation"], r["setting"], r["hypothesis"]): r for r in rows}

    beta = by[("beta", "0.5", "H1a")]
    assert (beta["baseline_value"], beta["value"]) == (0.5, 0.0)
    assert (beta["baseline_verdict"], beta["verdict"]) == ("supported", "not_supported")
    assert beta["verdict_changes"] is True
    assert by[("tnorm", "min", "H1a")]["verdict_changes"] is False

    assert by[("min_transfer", "1", "H2a")]["verdict_changes"] is False
    assert by[("min_transfer", "4", "H2a")]["verdict"] == "not_supported"

    # The vocabulary edit reached the experiment through a temporary vocabulary file.
    assert by[("delay_breakpoints", "-1", "H3c")]["value"] == 0.0  # on_time c: 1 - 1
    assert by[("delay_breakpoints", "+1", "H3c")]["value"] == 2.0
    assert by[("crisp_late", "official_ge_3", "H3c")]["value"] == 2.0  # c = 1, official = 1

    # No runtime in the main table, so it stays deterministic; runtimes are separate.
    assert all("runtime_s" not in r for r in rows)
    runtimes = ablations.runtime_table(fake_experiments).rows
    assert {(r["ablation"], r["setting"]) for r in runtimes} == {
        (a.name, a.setting) for a in ablations.ablations(_config())
    }
    assert all(r["runtime_s"] >= 0 for r in runtimes)


def test_temperature_ablation_keeps_only_that_temperature(monkeypatch):
    from urban_computing.evaluation import srq3

    runs = [SimpleNamespace(temperature=t, name=i) for i, t in enumerate([0.0, 0.7, 0.0])]
    missing = [("stats_only", 0.7, 1, "q1"), ("stats_only", 0.0, 2, "q2")]
    base = Context(_config(), True, {}, 1)
    base.cache["srq3_runs"] = srq3._StudyRuns(runs, missing)
    study = ablations._temperature_runs(base, 0.0)
    assert [r.name for r in study.runs] == [0, 2]
    assert study.missing_primary_completions == [("stats_only", 0.0, 2, "q2")]
