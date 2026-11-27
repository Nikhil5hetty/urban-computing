"""UC-051 experiment tests using fixed JSONL questions and synthetic inputs."""

import csv
import shutil
from pathlib import Path

import pandas as pd
import pytest
import yaml

from tests import factories
from urban_computing.evaluation import srq2
from urban_computing.evaluation.registry import Context
from urban_computing.evaluation.run import run

ROOT = Path(__file__).resolve().parents[1]


def _write_questions(path, questions):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(q.model_dump_json() for q in questions) + "\n", encoding="utf-8")


@pytest.fixture
def study(tmp_path, monkeypatch):
    config = yaml.safe_load((ROOT / "config/study.yaml").read_text(encoding="utf-8"))
    path = tmp_path / "fixed.jsonl"
    config["evaluation"]["questions_file"] = str(path)
    context = Context(config, False, {"vocabulary": str(ROOT / "config/vocabulary.yaml")}, 1)
    pairs = [1.75] * 4 + [4.0] * 16
    connections = pd.concat(
        [
            factories.connections(pairs),
            factories.connections(pairs, dep_line="IR17"),
            factories.connections(pairs, arr_line="IC2"),
        ],
        ignore_index=True,
    )
    arrivals = pd.concat(
        [
            factories.arrivals([3.0] + [0.0] * 19, stop_name="Display-name variant"),
            factories.arrivals([9.0] * 20, stop_id="8599999"),
        ],
        ignore_index=True,
    )
    monkeypatch.setattr(
        srq2, "_i4_tables", lambda ctx: (arrivals, connections, {"Olten": ["8500218"]})
    )
    return context, path


def test_fixed_question_cells_and_word_flips(study):
    ctx, path = study
    q = factories.sample_question
    questions = [q(margin_min=m, question_id=f"m{m}") for m in (3, 4, 5, 6, 8)]
    questions += [
        q(dep_line="IR17", question_id="second-route"),
        q(arr_product="IC", question_id="duplicate-cell"),  # arr_line takes precedence
        q(arr_line="IC2", question_id="no-official-cohort"),
        q(arr_line="IC3", question_id="no-data"),
    ]
    _write_questions(path, questions)

    h2a = srq2.h2a(ctx)
    assert h2a.point == 0.5
    assert (h2a.ci_low, h2a.ci_high) == pytest.approx((0.1876163, 0.8123837))
    assert h2a.details["n_questions"] == 9
    assert h2a.details["n_cells"] == 8
    assert h2a.details["n_compared"] == 6
    assert h2a.details["n_flips"] == 3
    assert h2a.details["excluded"] == {"no_fuzzy_verdict": 1, "no_crisp_verdict": 1}
    # The crisp late share is 0.05 while the fuzzy missed share at margins >= 5 is
    # zero. These are still agreements because both decision words are safe.
    assert h2a.details["flip_matrix"] == {
        "safe": {"safe": 3, "at_risk": 3, "risky": 0},
        "at_risk": {"safe": 0, "at_risk": 0, "risky": 0},
        "risky": {"safe": 0, "at_risk": 0, "risky": 0},
    }

    h2b = srq2.h2b(ctx)
    assert h2b.point == 1.0
    assert h2b.p == pytest.approx(0.1)  # two-sided Fisher test on [[3, 0], [0, 2]]
    assert h2b.details == {
        "short": {"n": 3, "n_flips": 3, "flip_rate": 1.0},
        "long": {"n": 2, "n_flips": 0, "flip_rate": 0.0},
        "n_between": 1,
    }

    sensitivity = srq2.transfer_sensitivity(ctx).rows
    assert [row["min_transfer_minutes"] for row in sensitivity] == [1, 2, 3, 4]
    assert [row["n"] for row in sensitivity] == [6] * 4
    assert [row["n_flips"] for row in sensitivity] == [1, 3, 4, 5]
    assert [row["flip_rate"] for row in sensitivity] == pytest.approx([1 / 6, 0.5, 4 / 6, 5 / 6])
    assert ctx.config["connections"]["min_transfer_minutes_default"] == 2

    examples = srq2.examples(ctx).rows
    assert [row["question_id"] for row in examples] == ["m3", "m4", "second-route"]
    for example in examples:
        assert (example["crisp_decision"], example["fuzzy_decision"]) == ("safe", "at_risk")
        assert "safe" in example["text"] and "at risk" in example["text"]
        assert example["explanation"] in example["text"]
        assert example["n"] == 20


def test_borderline_fixture_produces_a_flip_in_the_runner(tmp_path, monkeypatch):
    for directory in ("config", "eval", "tests/fixtures"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    monkeypatch.chdir(tmp_path)
    q = factories.sample_question(hub="Zürich HB", dep_line=None, weekday_group="all", margin_min=6)
    _write_questions(Path("eval/questions.jsonl"), [q])

    results = run(Path("config/study.yaml"), sample=True, only="srq2")
    assert results["invariants"]["I4"] == "pass"
    h2a = results["hypotheses"]["H2a"]
    assert h2a["point"] == 1.0 and h2a["details"]["flip_matrix"]["risky"]["safe"] == 1
    h2b = results["hypotheses"]["H2b"]
    assert h2b["point"] is None and h2b["p"] is None
    assert set(results["tables"]) == {"srq2_examples", "srq2_transfer_sensitivity"}
    with Path("results", results["tables"]["srq2_examples"]).open(encoding="utf-8") as stream:
        [example] = csv.DictReader(stream)
    assert (example["hub"], example["crisp_decision"], example["fuzzy_decision"]) == (
        "Zürich HB",
        "risky",
        "safe",
    )


def test_arrival_fallback_is_counted_and_unchanged_across_transfer_times(study):
    ctx, path = study
    _write_questions(path, [factories.sample_question(dep_line="IR404", margin_min=1)])

    h2a = srq2.h2a(ctx)
    assert h2a.details["n_fallback"] == h2a.details["n_compared"] == 1
    assert h2a.details["flip_matrix"]["safe"]["risky"] == 1
    assert [row["flip_rate"] for row in srq2.transfer_sensitivity(ctx).rows] == [1.0] * 4


def test_missing_fixed_questions_have_no_sample_estimates(study):
    ctx, _ = study
    with pytest.raises(FileNotFoundError, match="make questions"):
        srq2.h2a(ctx)

    ctx.sample = True
    h2a = srq2.h2a(ctx)
    assert h2a.point is None and h2a.ci_low is None and h2a.ci_high is None
    assert h2a.details["n_cells"] == h2a.details["n_compared"] == 0
    assert h2a.details["reason"] == "missing_question_set"
    assert srq2.examples(ctx).rows == []
