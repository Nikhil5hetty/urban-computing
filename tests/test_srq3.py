"""SRQ3 tests with synthetic observations and stored UC-040-format completions."""

import csv
import json
import shutil
from itertools import product
from pathlib import Path

import pandas as pd
import pytest
import yaml

from tests import factories
from urban_computing.evaluation import srq3
from urban_computing.evaluation.questions import write_questions
from urban_computing.evaluation.registry import Context
from urban_computing.evaluation.run import run, verdict

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def study(tmp_path, monkeypatch):
    config = yaml.safe_load((ROOT / "config/study.yaml").read_text(encoding="utf-8"))
    config["data"]["interim_dir"] = str(tmp_path)
    question = factories.sample_question(weekday_group="weekday")
    path = tmp_path / "questions.jsonl"
    config["evaluation"]["questions_file"] = str(path)
    write_questions([question, question.model_copy(update={"question_id": "q2"})], path)

    arrivals = pd.concat(
        [
            factories.arrivals([3.0] * 6 + [0.0] * 4, stop_name="Different display name"),
            factories.arrivals([15.0], stop_id="8599999"),
            factories.arrivals([15.0], time_band="night"),
        ]
    )
    pairs = pd.concat(
        [
            factories.connections([1.75, 1.75, 0, None, None, 4, 4, 4]),
            factories.connections([None], b_cancelled=False),
            factories.connections([None], dep_line="IR17"),
        ]
    )
    monkeypatch.setattr(srq3, "_i4_tables", lambda ctx: (arrivals, pairs, {"Olten": ["8500218"]}))
    ctx = Context(
        config,
        False,
        {"vocabulary": str(ROOT / "config/vocabulary.yaml"), "interim_dir": str(tmp_path)},
        1,
    )
    return ctx, question.question_id


def _write_outputs(ctx, condition, temperature, seed, outputs, **metadata):
    settings = ctx.config["llm"]
    model = settings["model_id"]
    base = Path(ctx.config["data"]["interim_dir"]) / "llm"
    path = base / condition / model.replace("/", "--") / str(temperature) / f"{seed}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "question_id": qid,
            "raw_output": output,
            "condition": condition,
            "temperature": temperature,
            "seed": seed,
            "model_id": model,
            "model_revision": settings["model_revision"],
            "max_new_tokens": settings["max_new_tokens"],
            "mock": False,
            **metadata,
        }
        for qid, output in outputs
    ]
    path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")
    return path


def _write_primary_outputs(ctx, question_ids, overrides):
    settings = ctx.config["llm"]
    return {
        (condition, temperature, seed): _write_outputs(
            ctx,
            condition,
            temperature,
            seed,
            [(qid, overrides.get((condition, temperature, seed, qid), "")) for qid in question_ids],
        )
        for condition, temperature, seed in product(
            settings["conditions"], settings["temperatures"], settings["seeds"]
        )
    }


def test_stored_outputs_metrics_pairing_breakdown_and_examples(study):
    ctx, qid = study
    stats, grounded = "stats_only", "fuzzy_grounded"
    false_claim = "Most trains are slightly late."
    true_claim = "Few trains are very late."
    _write_primary_outputs(
        ctx,
        (qid, "q2"),
        {
            (stats, 0.0, 1, qid): (
                f"{false_claim} About half of connections are missed. About half are delayed. "
                "Few trains are very late on Fridays."
            ),
            (stats, 0.0, 1, "q2"): false_claim,
            (
                grounded,
                0.0,
                1,
                qid,
            ): f"{true_claim} About half are delayed. Few connections are missed.",
            (grounded, 0.0, 1, "q2"): true_claim,
            (stats, 0.7, 2, qid): true_claim,
            (grounded, 0.7, 2, qid): true_claim,
            (stats, 0.7, 1, qid): false_claim,
        },
    )
    _write_outputs(ctx, "query_tool", 0.0, 1, [(qid, "Few trains are on time.")])

    a = srq3.h3a(ctx)
    assert a.point == 3 / 5
    assert (a.ci_low, a.ci_high) == pytest.approx((0.2307243, 0.8823792))
    assert a.details["n_claims"] == 7
    assert a.details["n_no_fuzzy_truth"] == 2
    assert a.details["unverifiable_rate"] == 1 / 7

    b = srq3.h3b(ctx)
    assert b.point == pytest.approx(1 / 4 - 3 / 5)
    assert b.p == pytest.approx(0.5)
    assert b.details["n_paired_slots"] == 3
    assert b.details["n_unscorable_pairs"] == 2
    assert b.details["unpaired_slots"] == {stats: 2, grounded: 0}
    assert b.details["n_paired_questions"] == 2
    assert b.details["wilcoxon_p"] == pytest.approx(0.5)

    c = srq3.h3c(ctx)
    assert c.point == 4 / 10
    assert (c.ci_low, c.ci_high) == pytest.approx((0.1681803, 0.6873262))
    assert c.details["crisp_true_fuzzy_false"] == 3
    assert c.details["crisp_false_fuzzy_true"] == 1
    assert c.details["crisp_true_fuzzy_false_rate"] == 0.3
    assert c.details["crisp_false_fuzzy_true_rate"] == 0.1

    rows = srq3.breakdown(ctx).rows
    keyed = {(row["condition"], row["temperature"], row["seed"]): row for row in rows}
    assert keyed[stats, 0.7, None]["false_share"] == 0.5
    assert keyed[stats, None, 1]["n_outputs"] == 4
    assert keyed[stats, 0.7, 2]["false_share"] == 0
    assert keyed["query_tool", None, None]["false_share"] == 1

    examples = srq3.examples(ctx).rows
    assert len(examples) == 5
    assert [row["distance_to_threshold"] for row in examples] == sorted(
        row["distance_to_threshold"] for row in examples
    )
    cancelled = next(row for row in examples if row["quantifier"] == "about_half")
    assert cancelled["n"] == 8  # includes both cancellations, excludes the unknown gap
    assert (cancelled["p_crisp"], cancelled["p_fuzzy"]) == (5 / 8, 0.5)
    assert cancelled["disagreement"] == "crisp_false_fuzzy_true"
    assert all(row["text"] and row["question_id"] and row["condition"] for row in examples)


def test_missing_or_empty_completions_have_no_estimates(study):
    ctx, qid = study
    a = srq3.h3a(ctx)
    assert a.point is None
    assert a.details["n_missing_primary_completions"] == 24
    assert srq3.h3b(ctx).p is None
    assert srq3.h3c(ctx).point is None
    assert srq3.examples(ctx).rows == []

    _write_primary_outputs(ctx, (qid, "q2"), {})
    ctx.cache.clear()
    a = srq3.h3a(ctx)
    assert a.point is None and a.details["unverifiable_rate"] is None
    assert a.details["n_outputs"] == a.details["n_outputs_without_claims"] == 12


@pytest.mark.parametrize("missing", ["run", "question", "truncated_question"])
def test_incomplete_primary_inputs_withhold_hypothesis_verdicts(study, missing):
    ctx, qid = study
    paths = _write_primary_outputs(
        ctx,
        (qid, "q2"),
        {
            ("stats_only", 0.0, 1, qid): "Most trains are slightly late.",
            ("fuzzy_grounded", 0.0, 1, qid): "Few trains are very late.",
        },
    )
    expected = []
    for condition in sorted(ctx.config["llm"]["conditions"]):
        path = paths[condition, 0.7, 2]
        if missing == "run":
            path.unlink()
        else:
            first, second = path.read_bytes().splitlines(keepends=True)
            tail = second[:20] + b"\xc3" if missing == "truncated_question" else b""
            path.write_bytes(first + tail)
        expected.extend(
            {"condition": condition, "temperature": 0.7, "seed": 2, "question_id": question_id}
            for question_id in (sorted([qid, "q2"]) if missing == "run" else ["q2"])
        )

    specs = yaml.safe_load((ROOT / "eval/hypotheses.yaml").read_text(encoding="utf-8"))
    by_id = {spec["id"]: spec for spec in specs["hypotheses"]}
    for key, experiment in (("H3a", srq3.h3a), ("H3b", srq3.h3b), ("H3c", srq3.h3c)):
        result = experiment(ctx)
        assert (result.point, result.ci_low, result.ci_high, result.p) == (None,) * 4
        assert verdict(by_id[key], result) == "inconclusive"
        assert result.details["n_missing_primary_completions"] == len(expected)
        assert result.details["missing_primary_completions"] == expected
    assert srq3.breakdown(ctx).rows


@pytest.mark.parametrize("field, value", [("model_revision", "0" * 40), ("max_new_tokens", 100)])
def test_rejects_outputs_generated_with_different_model_settings(study, field, value):
    ctx, qid = study
    _write_outputs(ctx, "stats_only", 0.0, 1, [(qid, "")], **{field: value})
    with pytest.raises(ValueError, match=field):
        srq3.h3a(ctx)


@pytest.mark.parametrize("duplicate", [True, False])
def test_rejects_duplicate_and_unknown_questions(study, duplicate):
    ctx, qid = study
    second = qid if duplicate else "stale-question"
    _write_outputs(ctx, "stats_only", 0.0, 1, [(qid, ""), (second, "")])
    with pytest.raises(
        ValueError, match="Duplicate completion" if duplicate else "unknown question"
    ):
        srq3.h3a(ctx)


def test_mock_fixture_runs_through_project_runner(tmp_path, monkeypatch):
    for directory in ("config", "eval", "tests/fixtures"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    monkeypatch.chdir(tmp_path)

    mock_calls = []
    write_completions = srq3.runner.run

    def run_mock(questions_path, condition, model_id, temperature, seed, out_dir, mock=False):
        assert mock is True
        mock_calls.append((condition, temperature, seed))
        return write_completions(
            questions_path, condition, model_id, temperature, seed, out_dir, mock=mock
        )

    monkeypatch.setattr(srq3.runner, "run", run_mock)
    result = run(Path("config/study.yaml"), sample=True, only="srq3")
    config = yaml.safe_load(Path("config/study.yaml").read_text(encoding="utf-8"))["llm"]
    assert set(mock_calls) == {
        (condition, temperature, seed)
        for condition in config["conditions"]
        for temperature in config["temperatures"]
        for seed in config["seeds"]
    }
    assert result["invariants"] == {"I1": "pass", "I2": "pass", "I4": "pass", "I5": "fail"}
    assert result["hypotheses"]["H3a"]["verdict"] == "blocked_by_invariant"
    assert result["hypotheses"]["H3a"]["details"]["n_outputs"] > 0
    assert result["hypotheses"]["H3b"]["details"]["n_paired_slots"] > 0
    assert result["hypotheses"]["H3c"]["details"]["n_compared"] > 0
    assert set(result["tables"]) == {"srq3_breakdown", "srq3_examples"}
    with Path("results", result["tables"]["srq3_breakdown"]).open(encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert {row["condition"] for row in rows} == {"stats_only", "fuzzy_grounded"}
    assert not Path("data/interim/llm-mock").exists()
