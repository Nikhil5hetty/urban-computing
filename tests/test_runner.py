"""Project runner integration tests with synthetic experiment providers."""

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import yaml

from tests.factories import arrivals
from urban_computing.evaluation import registry
from urban_computing.evaluation.run import run, verdict

ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path("config/study.yaml")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    for directory in ("config", "eval", "tests/fixtures"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(registry, "EXPERIMENT_MODULES", ())
    for store in ("EXPERIMENTS", "INVARIANTS", "TABLES"):
        monkeypatch.setattr(registry, store, {})
    return tmp_path


def test_schema_and_reproducibility(workspace):
    for key in ("I4", "I5"):
        registry.invariant(key)(lambda ctx: registry.InvariantResult(True))

    @registry.experiment("H1a")
    def measure(ctx):
        assert ctx.sample
        assert ctx.seed == ctx.config["study"]["seed"]
        assert Path(ctx.paths["ground_truth"]).is_file()
        assert list(Path(ctx.paths["raw_dir"]).glob("*.csv"))
        assert not Path(ctx.paths["arrivals"]).exists()
        delays = arrivals([0.0, 3.0, 4.0])["delay_min"]
        return registry.Result(point=delays.ge(3).mean(), ci_low=0.1, ci_high=0.9)

    @registry.table("example")
    def example(ctx):
        return registry.Table("example", [{"count": 3}, {"count": 1, "note": "example"}])

    path = workspace / "results/results.json"
    run(CONFIG, sample=True)
    first = json.loads(path.read_bytes())
    run(CONFIG, sample=True)
    second = json.loads(path.read_bytes())
    assert first["meta"].pop("timestamp")
    assert second["meta"].pop("timestamp")
    assert first == second

    preregistration = yaml.safe_load(Path("eval/hypotheses.yaml").read_text())
    assert set(first) == {"hypotheses", "invariants", "tables", "meta"}
    assert set(first["hypotheses"]) == {spec["id"] for spec in preregistration["hypotheses"]}
    assert first["invariants"] == {"I1": "pass", "I2": "pass", "I4": "pass", "I5": "pass"}
    assert first["hypotheses"]["H1a"] == {
        "point": pytest.approx(2 / 3),
        "ci_low": 0.1,
        "ci_high": 0.9,
        "p": None,
        "value": None,
        "details": {},
        "verdict": "supported",
    }
    assert first["hypotheses"]["H1b"]["verdict"] == "not_run"
    assert set(first["meta"]) >= {"git_sha", "config_hash", "versions"}
    assert first["tables"] == {"example": "tables/example.csv"}
    assert (workspace / "results/tables/example.csv").read_text() == ("count,note\n3,\n1,example\n")
    assert (workspace / "results/REPORT.md").is_file()


def test_failed_invariant_runs_first_and_blocks_verdict(workspace, monkeypatch):
    from urban_computing.fuzzy import truth

    monkeypatch.setattr(truth, "truth_simple", lambda memberships, quantifier: 0.0)
    events = []
    registry.invariant("I5")(lambda ctx: registry.InvariantResult(True))

    @registry.invariant("I4")
    def gate(ctx):
        events.append("invariant")
        return registry.InvariantResult(False, {"reason": "fixture mismatch"})

    @registry.experiment("H1b")
    def experiment(ctx):
        events.append("experiment")
        return registry.Result(value=np.int64(3), p=np.float64(np.nan))

    result = run(CONFIG, sample=True)
    assert events == ["invariant", "experiment"]
    assert result["invariants"]["I1"] == "fail"
    assert result["hypotheses"]["H1b"]["verdict"] == "blocked_by_invariant"
    assert result["hypotheses"]["H1b"]["value"] == 3
    assert result["hypotheses"]["H1b"]["p"] is None
    assert result["hypotheses"]["H1a"]["verdict"] == "not_run"
    report = (workspace / "results/REPORT.md").read_text()
    assert report.splitlines()[2] == "## Invariant failures"
    assert "fixture mismatch" in report


@pytest.mark.parametrize("only", [None, "srq1"])
def test_missing_required_invariant_blocks_verdict(workspace, monkeypatch, only):
    from urban_computing.evaluation import run as runner

    invariant_module = "urban_computing.evaluation.invariants"
    srq1 = "urban_computing.evaluation.srq1"
    monkeypatch.setattr(registry, "EXPERIMENT_MODULES", (invariant_module, srq1))
    events = []

    def import_provider(name):
        if name == invariant_module:
            registry.invariant("I5")(check)
        elif name == srq1:
            registry.experiment("H1b")(measure)

    def check(ctx):
        events.append("I5")
        return registry.InvariantResult(True)

    def measure(ctx):
        events.append("H1b")
        return registry.Result(value=1)

    measure.__module__ = srq1
    check.__module__ = invariant_module
    monkeypatch.setattr(runner, "import_module", import_provider)
    result = run(CONFIG, sample=True, only=only)
    assert events == ["I5", "H1b"]
    assert result["invariants"] == {"I1": "pass", "I2": "pass", "I5": "pass"}
    assert result["hypotheses"]["H1b"]["verdict"] == "blocked_by_invariant"
    report = (workspace / "results/REPORT.md").read_text()
    assert report.splitlines()[2] == "## Required invariants not run: I4"
    assert "I6 is checked by the paper export (UC-070)." in report


def test_unimplemented_invariant_raises(workspace):
    @registry.invariant("I1")
    def gate(ctx):
        raise NotImplementedError("UC-021")

    with pytest.raises(NotImplementedError, match="UC-021"):
        run(CONFIG, sample=True)


def test_only_imports_and_runs_selected_module(workspace, monkeypatch):
    from urban_computing.evaluation import run as runner

    ablations, srq1 = "urban_computing.evaluation.ablations", "urban_computing.evaluation.srq1"
    monkeypatch.setattr(registry, "EXPERIMENT_MODULES", (srq1, ablations))
    imported = []

    def import_provider(name):
        imported.append(name)

    monkeypatch.setattr(runner, "import_module", import_provider)

    @registry.table("ablations")
    def selected(ctx):
        return registry.Table("ablations", [{"value": 1}])

    @registry.experiment("H1a")
    def unrelated(ctx):
        pytest.fail("Unselected experiment ran")

    selected.__module__ = ablations
    unrelated.__module__ = srq1
    result = run(CONFIG, sample=True, only="ablations")
    assert imported == [ablations]
    assert result["tables"] == {"ablations": "tables/ablations.csv"}
    assert result["hypotheses"]["H1a"]["verdict"] == "not_run"


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (registry.Result(point=0.2, ci_low=0.03), "supported"),
        (registry.Result(point=0.01), "not_supported"),
        (registry.Result(point=0.10, ci_low=0.02), "inconclusive"),
        (registry.Result(point=0.2), "inconclusive"),
    ],
)
def test_preregistered_verdicts(result, expected):
    assert (
        verdict(
            {
                "id": "H1a",
                "supported_if": "point >= 0.10 and ci_low > 0.02",
                "not_supported_if": "point < 0.02",
            },
            result,
        )
        == expected
    )


@pytest.mark.parametrize(
    "rule", ["point > 0 or __import__('os')", "point.real > 0", "unknown >= 0", "point + 1 > 0"]
)
def test_verdict_rejects_unknown_syntax(rule):
    with pytest.raises(ValueError, match="Unsupported verdict"):
        verdict({"supported_if": rule, "not_supported_if": "point < 0"}, registry.Result(point=1))


def test_registry_rejects_duplicate_ids(workspace):
    decorate = registry.experiment("H1a")
    first = decorate(lambda ctx: registry.Result())
    assert decorate(first) is first
    with pytest.raises(ValueError, match="H1a registered twice"):
        decorate(lambda ctx: registry.Result())


def test_missing_transitive_dependency_is_reported(workspace, monkeypatch):
    from urban_computing.evaluation import run as runner

    def import_provider(name):
        raise ModuleNotFoundError(name="dependency_inside_provider")

    monkeypatch.setattr(registry, "EXPERIMENT_MODULES", ("example_provider",))
    monkeypatch.setattr(runner, "import_module", import_provider)
    with pytest.raises(ModuleNotFoundError) as exc:
        run(CONFIG, sample=True)
    assert exc.value.name == "dependency_inside_provider"


def test_real_mode_checks_the_manifest_without_accessing_raw_data(workspace, monkeypatch):
    from urban_computing.data import download

    seen = []

    def verify_manifest(path):
        seen.append(path)
        return ["raw/ist-daten/example.csv"]

    monkeypatch.setattr(download, "verify_manifest", verify_manifest)

    @registry.experiment("H1b")
    def count(ctx):
        assert not ctx.sample
        assert ctx.paths["raw_dir"] == ctx.config["data"]["raw_dir"]
        assert ctx.paths["arrivals"] == "data/processed/arrivals.parquet"
        return registry.Result(value=1)

    result = run(CONFIG)
    assert seen == [Path("data/MANIFEST.json")]
    assert result["invariants"]["I3"] == "fail"
    assert result["hypotheses"]["H1b"]["verdict"] == "blocked_by_invariant"
