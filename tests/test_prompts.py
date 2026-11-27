"""Snapshot, integration, and optional GPU checks for the UC-040 runner."""

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

from scripts import run_llm
from tests import factories
from urban_computing.assistant import engine
from urban_computing.llm import runner
from urban_computing.llm.parser import load_lexicon, parse_output
from urban_computing.llm.prompts import render_prompt

QUESTION = """\
You are writing for a passenger using Swiss public transport.
Question: How reliable is my transfer at Olten from IC1 to IR16 with 4 minutes to change?
Time band: morning peak. Days: Mondays.
"""
INSTRUCTIONS = """\
Write a citizen answer of at most three sentences.
Use only these quantifiers: few, about half, most.
Use only these outcome words: on time, slightly late, late, very late, missed, tight, comfortable.
Use only claims supported by the evidence and keep their scope.
If the evidence cannot support a claim in this vocabulary, leave it out.
Return one JSON object followed by the same citizen answer as plain text:
{"claims": [{"quantifier": "...", "summarizer": "...", "restriction": null}], "text": "..."}
Use null for the question's own segment, or name the narrower restriction in words.
Include one entry per quantified claim in the text. Use an empty claims list if there are none."""


def test_stats_only_prompt_snapshot():
    stats = {"n": 5, "mean_delay_min": 1.25, "share_missed": 0.2}
    assert render_prompt("stats_only", factories.sample_question(), stats=stats) == (
        QUESTION
        + "Segment statistics (delays in minutes, shares from 0 to 1):\n"
        + '{"mean_delay_min": 1.25, "n": 5, "share_missed": 0.2}\n\n'
        + INSTRUCTIONS
    )


def test_fuzzy_grounded_prompt_snapshot():
    answer = factories.sample_answer()
    assert render_prompt("fuzzy_grounded", answer.question, answer=answer) == (
        QUESTION
        + "Assistant decision: at risk.\n"
        + "Supported explanations (truth from 0 to 1):\n"
        + "- Few of your connections at Olten are missed. (truth 0.74, n=38)\n\n"
        + INSTRUCTIONS
    )


def test_prompt_requires_condition_evidence():
    q = factories.sample_question()
    for condition in ("stats_only", "fuzzy_grounded", "query_tool"):
        with pytest.raises(ValueError, match=condition):
            render_prompt(condition, q)
    with pytest.raises(ValueError, match="question"):
        render_prompt(
            "fuzzy_grounded",
            q,
            answer=factories.sample_answer(question=q.model_copy(update={"hub": "Bern"})),
        )


@pytest.fixture
def questions_path(tmp_path):
    path = tmp_path / "questions.jsonl"
    path.write_text(
        "".join(
            factories.sample_question(question_id=f"q{i}").model_dump_json() + "\n"
            for i in range(2)
        ),
        encoding="utf-8",
    )
    return path


def _records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_mock_cli_matrix_is_reproducible_and_parseable(questions_path, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.setitem(sys.modules, "transformers", None)

    config = yaml.safe_load(runner.STUDY_CONFIG.read_text(encoding="utf-8"))["llm"]
    assert config["model_revision"] == "b946d40447b2b597999b9c86d44bee0b452c919f"
    roots = [tmp_path / "first", tmp_path / "second"]
    for root in roots:
        run_llm.main(["--mock", "--questions", str(questions_path), "--out-dir", str(root)])

    paths = sorted(path.relative_to(roots[0]) for path in roots[0].rglob("*.jsonl"))
    assert {str(path) for path in paths} == {
        f"{condition}/{config['model_id'].replace('/', '--')}/{temperature}/{seed}.jsonl"
        for condition in config["conditions"]
        for temperature in config["temperatures"]
        for seed in config["seeds"]
    }
    lexicon = load_lexicon()
    for path in paths:
        assert (roots[0] / path).read_bytes() == (roots[1] / path).read_bytes()
        records = _records(roots[0] / path)
        assert [row["question_id"] for row in records] == ["q0", "q1"]
        for row in records:
            assert row["mock"]
            assert row["model_revision"] == config["model_revision"]
            assert row["parse_status"] == "json"
            assert row["elapsed_seconds"] == 0.0
            assert len(row["prompt_hash"]) == 64
            claims = parse_output(row["question_id"], row["raw_output"], lexicon)
            assert [(claim.quantifier, claim.summarizer, claim.status) for claim in claims] == [
                ("few", "connection_slack_minutes:missed", "ok")
            ]


def test_runner_uses_both_evidence_sources_and_resume(questions_path, tmp_path, monkeypatch):
    config = yaml.safe_load(runner.STUDY_CONFIG.read_text(encoding="utf-8"))
    config["data"]["processed_dir"] = str(tmp_path)
    config["connections"]["hub_stop_ids"] = {"Olten": ["8500218"]}
    revision = "a" * 40
    config["llm"]["model_revision"] = revision
    config_path = tmp_path / "study.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr(runner, "STUDY_CONFIG", config_path)
    arrivals = pd.concat(
        [
            factories.arrivals([0, 3, 6, None], stop_name="Alternate spelling"),
            factories.arrivals([50], line="IC8"),
            factories.arrivals([100], stop_id="8507000"),
        ],
        ignore_index=True,
    )
    pairs = pd.concat(
        [
            factories.connections([3, 1, -1, None]),
            factories.connections([None], b_cancelled=False),
            factories.connections([0], dep_line="IR17"),
        ],
        ignore_index=True,
    )
    arrivals.to_parquet(tmp_path / "arrivals.parquet")
    pairs.to_parquet(tmp_path / "connections.parquet")

    def answer(question, connections, arrivals, vocab, config):
        assert len(connections) == 6
        assert len(arrivals) == 6
        return factories.sample_answer(question=question)

    monkeypatch.setattr(engine, "answer", answer)
    prompts = []
    fail = True

    def model_generator(model_id, loaded_revision, temperature, seed, max_new_tokens):
        assert loaded_revision == revision
        assert model_id == config["llm"]["model_id"]
        assert temperature == 0.0
        assert seed == config["llm"]["seeds"][0]
        assert max_new_tokens == config["llm"]["max_new_tokens"]

        def generate(prompt):
            if fail and len(prompts) == 1:
                raise RuntimeError("interrupted")
            prompts.append(prompt)
            if len(prompts) == 2:
                return '{"claims": ['
            return "Few connections are missed."

        return generate, {"torch": "fixture"}

    monkeypatch.setattr(runner, "_model_generator", model_generator)
    model, seed = config["llm"]["model_id"], config["llm"]["seeds"][0]
    output = tmp_path / "outputs"
    with pytest.raises(RuntimeError, match="interrupted"):
        runner.run(questions_path, "stats_only", model, 0.0, seed, output)
    path = next(output.rglob("*.jsonl"))
    original = path.read_bytes()
    assert len(_records(path)) == 1
    with path.open("ab") as stream:
        stream.write(b'{"question_id":"q1","raw_output":')
    fail = False
    assert runner.run(questions_path, "stats_only", model, 0.0, seed, output) == path
    assert path.read_bytes().startswith(original)
    assert len(prompts) == 2
    evidence = json.loads(prompts[0].splitlines()[4])
    assert evidence == {
        "n": 3,
        "mean_delay_min": 3.0,
        "median_delay_min": 3.0,
        "p90_delay_min": 5.4,
        "punctual_threshold_min": 3.0,
        "share_at_or_above_threshold": 2 / 3,
        "n_connections": 4,
        "share_missed": 0.75,
    }
    first, second = _records(path)
    assert first["model_revision"] == second["model_revision"] == revision
    assert second["prompt_hash"] == hashlib.sha256(prompts[1].encode()).hexdigest()
    assert first["parse_status"] == "free_text"
    assert second["parse_status"] == "invalid_json"
    assert second["raw_output"] == '{"claims": ['

    fuzzy_path = runner.run(questions_path, "fuzzy_grounded", model, 0.0, seed, output)
    assert len(prompts) == 4
    assert "Few of your connections at Olten are missed. (truth 0.74, n=38)" in prompts[-1]
    assert "Segment statistics" not in prompts[-1]

    def unexpected_load(*args):
        pytest.fail("a complete run loaded a model")

    monkeypatch.setattr(runner, "_model_generator", unexpected_load)
    before = fuzzy_path.read_bytes()
    assert runner.run(questions_path, "fuzzy_grounded", model, 0.0, seed, output) == fuzzy_path
    assert fuzzy_path.read_bytes() == before

    config["llm"]["model_revision"] = "b" * 40
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="different settings"):
        runner.run(questions_path, "fuzzy_grounded", model, 0.0, seed, output)
    assert fuzzy_path.read_bytes() == before


def test_array_index_selects_one_configured_run(questions_path, tmp_path):
    run_llm.main(
        [
            "--mock",
            "--questions",
            str(questions_path),
            "--out-dir",
            str(tmp_path),
            "--array-index",
            "11",
        ]
    )
    output = list(tmp_path.glob("fuzzy_grounded/*/0.7/3.jsonl"))
    assert len(output) == 1
    assert len(list(tmp_path.rglob("3.jsonl"))) == 1


@pytest.mark.gpu
def test_apertus_greedy_smoke():
    import torch

    if not torch.cuda.is_available():
        pytest.skip("A CUDA GPU is required")
    settings = yaml.safe_load(Path(runner.STUDY_CONFIG).read_text(encoding="utf-8"))["llm"]
    generate, _ = runner._model_generator(
        settings["model_id"],
        runner.model_revision(settings),
        0.0,
        settings["seeds"][0],
        settings["max_new_tokens"],
    )
    answer = factories.sample_answer()
    prompt = render_prompt("fuzzy_grounded", answer.question, answer=answer)
    first = generate(prompt)
    assert first.strip()
    assert generate(prompt) == first
