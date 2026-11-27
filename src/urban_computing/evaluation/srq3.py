"""Audit stored LLM claims with the preregistered SRQ3 measures.

A claim keeps its parser slot even when it cannot be scored. McNemar pairs slots within
the same question, temperature and seed across the two primary conditions. Wilcoxon uses
one mean of the scored claims per question and condition. The false-share difference
uses all scored claims in each condition, including those without a scored counterpart.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from urban_computing.assistant.contract import Question
from urban_computing.assistant.engine import (
    VOCAB_PATH,
    connection_segment,
    hub_arrivals,
    own_arrivals,
    personal_slack,
)
from urban_computing.evaluation.invariants import _i4_questions, _i4_tables
from urban_computing.evaluation.questions import write_questions
from urban_computing.evaluation.registry import Context, Result, Table, experiment, table
from urban_computing.evaluation.stats import mcnemar, wilcoxon_paired, wilson_ci
from urban_computing.fuzzy.vocabulary import load_vocabulary
from urban_computing.llm import runner
from urban_computing.llm.checkers import FUZZY_TRUE_THRESHOLD, CheckResult, check
from urban_computing.llm.parser import claim_stats, load_lexicon, parse_output
from urban_computing.llm.prompts import CONDITIONS, STUDY_CONDITIONS

_STATS, _GROUNDED = STUDY_CONDITIONS
_DISAGREEMENTS = ("crisp_true_fuzzy_false", "crisp_false_fuzzy_true")


@dataclass
class _Run:
    condition: str
    temperature: float
    seed: int
    question: Question
    checks: list[CheckResult]


def _values(
    question: Question, arrivals: pd.DataFrame, connections: pd.DataFrame, min_transfer: float
) -> dict[str, np.ndarray]:
    """Encode values in minutes and row-aligned restriction columns for both checkers."""
    arrival_rows = own_arrivals(arrivals, question)
    connection_rows = connection_segment(question, connections)
    delay, slack = "arrival_delay_minutes", "connection_slack_minutes"
    values = {
        delay: arrival_rows["delay_min"].to_numpy(dtype=float, na_value=np.nan),
        slack: personal_slack(connection_rows, question.margin_min, min_transfer),
    }
    for attribute, rows in ((delay, arrival_rows), (slack, connection_rows)):
        for column in ("time_band", "weekday"):
            values[f"{attribute}.{column}"] = rows[column].to_numpy()
    return values


def _read_questions(path: Path, config: dict) -> dict[str, Question]:
    questions = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            question = Question.model_validate_json(line, context={"study_config": config})
            qid = question.question_id
            if not qid or not qid.strip() or qid in questions:
                raise ValueError(f"{path}:{line_number}: missing or duplicate question_id")
            questions[qid] = question
    return questions


def _stored_runs(ctx: Context, output_dir: Path, question_path: Path) -> list[_Run]:
    settings = ctx.config["llm"]
    model = settings["model_id"]
    model_dir = model.replace("/", "--")
    files = [
        (condition, path)
        for condition in CONDITIONS
        for path in sorted((output_dir / condition / model_dir).glob("*/*.jsonl"))
    ]
    if not files:
        return []

    questions = _read_questions(question_path, ctx.config)
    outputs: dict[tuple[str, float, int, str], str] = {}
    for condition, path in files:
        temperature, seed = float(path.parent.name), int(path.stem)
        if temperature not in settings["temperatures"] or seed not in settings["seeds"]:
            raise ValueError(f"{path}: temperature or seed is outside the study configuration")
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                location = f"{path}:{line_number}"
                if (
                    row["condition"] != condition
                    or row["model_id"] != model
                    or row["temperature"] != temperature
                    or row["seed"] != seed
                    or row["mock"] is not ctx.sample
                ):
                    raise ValueError(f"{location}: completion metadata does not match the run")
                qid = row["question_id"]
                if qid not in questions:
                    raise ValueError(f"{location}: unknown question {qid!r}")
                key = condition, temperature, seed, qid
                if key in outputs:
                    raise ValueError(f"{location}: Duplicate completion for {key!r}")
                outputs[key] = row["raw_output"]

    if not outputs:
        return []
    arrivals, connections, hub_ids = _i4_tables(ctx)
    connection_config = ctx.config["connections"].copy()
    if hub_ids and not connection_config.get("hub_stop_ids"):
        connection_config["hub_stop_ids"] = hub_ids
    config = {**ctx.config, "connections": connection_config}
    min_transfer = float(connection_config["min_transfer_minutes_default"])
    vocab = load_vocabulary(Path(ctx.paths.get("vocabulary", VOCAB_PATH)))
    lexicon = load_lexicon()

    # Work on one question at a time so its arrays can be shared across all completions.
    per_question = defaultdict(list)
    for (condition, temperature, seed, qid), raw in sorted(outputs.items()):
        per_question[qid].append((condition, temperature, seed, raw))

    runs = []
    hubs = {}
    for qid, completions in sorted(per_question.items()):
        question = questions[qid]
        if question.hub not in hubs:
            hubs[question.hub] = (
                hub_arrivals(question, arrivals, config),
                connections.loc[connections["hub"] == question.hub],
            )
        hub_rows, hub_pairs = hubs[question.hub]
        values = _values(question, hub_rows, hub_pairs, min_transfer)
        for condition, temperature, seed, raw in completions:
            checks = [
                check(claim, values, vocab, config) for claim in parse_output(qid, raw, lexicon)
            ]
            runs.append(_Run(condition, temperature, seed, question, checks))
    return runs


def _sample_runs(ctx: Context) -> list[_Run]:
    _, connections, _ = _i4_tables(ctx)
    with TemporaryDirectory(dir=ctx.paths["interim_dir"]) as scratch:
        question_path = Path(scratch) / "questions.jsonl"
        output_dir = Path(scratch) / "llm-mock"
        # Use I4's observed synthetic cells even if a real question file is present.
        config = {
            **ctx.config,
            "evaluation": {**ctx.config["evaluation"], "questions_file": str(question_path)},
        }
        questions = [
            question.model_copy(update={"question_id": f"sample-{index:04d}"})
            for index, question in enumerate(_i4_questions(connections, config), 1)
        ]
        if not questions:
            return []
        write_questions(questions, question_path)
        settings = ctx.config["llm"]
        for condition, temperature, seed in product(
            STUDY_CONDITIONS, settings["temperatures"], settings["seeds"]
        ):
            runner.run(
                question_path,
                condition,
                settings["model_id"],
                temperature,
                seed,
                output_dir,
                mock=True,
            )
        return _stored_runs(ctx, output_dir, question_path)


def _runs(ctx: Context) -> list[_Run]:
    if "srq3_runs" not in ctx.cache:
        if ctx.sample:
            runs = _sample_runs(ctx)
        else:
            questions = Path(ctx.config["evaluation"].get("questions_file", "eval/questions.jsonl"))
            runs = _stored_runs(ctx, Path(ctx.paths["interim_dir"]) / "llm", questions)
        ctx.cache["srq3_runs"] = runs
    return ctx.cache["srq3_runs"]


def _interval(count: int, total: int) -> tuple[float | None, float | None, float | None]:
    return wilson_ci(count, total) if total else (None, None, None)


def _false_share(runs: list[_Run]) -> Result:
    checks = [result for run in runs for result in run.checks]
    counts = claim_stats(result.claim for result in checks)
    n_scored = sum(result.fuzzy_true is not None for result in checks)
    n_false = sum(result.fuzzy_true is False for result in checks)
    point, low, high = _interval(n_false, n_scored)
    return Result(
        point=point,
        ci_low=low,
        ci_high=high,
        details={
            "n_outputs": len(runs),
            "n_outputs_without_claims": sum(not run.checks for run in runs),
            "n_claims": len(checks),
            "n_parsable": int(counts["ok"]),
            "n_unverifiable": int(counts["unverifiable"] + counts["unverifiable_causal"]),
            "n_inconsistent": int(counts["inconsistent"]),
            "unverifiable_rate": counts["unverifiable_rate"] if checks else None,
            "n_scored": n_scored,
            "n_false": n_false,
            "n_no_fuzzy_truth": len(checks) - n_scored,
        },
    )


@experiment("H3a")
def h3a(ctx: Context) -> Result:
    """Return the stats-only fuzzy-false proportion, 95% Wilson CI and unverifiable rate."""
    return _false_share([run for run in _runs(ctx) if run.condition == _STATS])


@experiment("H3b")
def h3b(ctx: Context) -> Result:
    """Return grounded minus stats-only false share and paired McNemar and Wilcoxon tests."""
    slots = {_STATS: {}, _GROUNDED: {}}
    truths = {_STATS: defaultdict(list), _GROUNDED: defaultdict(list)}
    primary_runs = [run for run in _runs(ctx) if run.condition in STUDY_CONDITIONS]
    for run in primary_runs:
        for result in run.checks:
            qid = result.claim.question_id
            slots[run.condition][qid, run.temperature, run.seed, result.claim.slot] = result
            if result.fuzzy is not None:
                truths[run.condition][qid].append(result.fuzzy)

    baseline, grounded = slots[_STATS], slots[_GROUNDED]
    matched = baseline.keys() & grounded.keys()
    paired = [
        (baseline[key].fuzzy_true, grounded[key].fuzzy_true)
        for key in sorted(matched)
        if baseline[key].fuzzy_true is not None and grounded[key].fuzzy_true is not None
    ]
    improved = paired.count((False, True))
    worsened = paired.count((True, False))
    paired_questions = sorted(truths[_STATS].keys() & truths[_GROUNDED].keys())
    means = [
        np.array([np.mean(truths[condition][qid]) for qid in paired_questions])
        for condition in STUDY_CONDITIONS
    ]
    rates = {
        condition: _false_share([run for run in primary_runs if run.condition == condition]).point
        for condition in STUDY_CONDITIONS
    }
    difference = None
    if rates[_GROUNDED] is not None and rates[_STATS] is not None:
        difference = rates[_GROUNDED] - rates[_STATS]
    return Result(
        point=difference,
        p=mcnemar(improved, worsened) if paired else None,
        details={
            "false_share": rates,
            "n_paired_slots": len(paired),
            "n_unscorable_pairs": len(matched) - len(paired),
            "unpaired_slots": {
                _STATS: len(baseline.keys() - grounded.keys()),
                _GROUNDED: len(grounded.keys() - baseline.keys()),
            },
            "stats_only_false_fuzzy_grounded_true": improved,
            "stats_only_true_fuzzy_grounded_false": worsened,
            "n_paired_questions": len(paired_questions),
            "wilcoxon_p": wilcoxon_paired(*means) if paired_questions else None,
        },
    )


def _disagreement(runs: list[_Run]) -> Result:
    counts = Counter(result.disagreement for run in runs for result in run.checks)
    n_disagreements = sum(counts[kind] for kind in _DISAGREEMENTS)
    n_compared = counts["none"] + n_disagreements
    point, low, high = _interval(n_disagreements, n_compared)
    details = {
        "n_compared": n_compared,
        "n_disagreements": n_disagreements,
        "n_uncomparable": counts["n/a"],
    }
    for kind in _DISAGREEMENTS:
        rate, ci_low, ci_high = _interval(counts[kind], n_compared)
        details[kind] = counts[kind]
        details[f"{kind}_rate"] = rate
        details[f"{kind}_ci_low"] = ci_low
        details[f"{kind}_ci_high"] = ci_high
    return Result(point=point, ci_low=low, ci_high=high, details=details)


@experiment("H3c")
def h3c(ctx: Context) -> Result:
    """Return the disagreement proportion, 95% Wilson CI and counts by checker outcome."""
    return _disagreement(_runs(ctx))


@table("srq3_breakdown")
def breakdown(ctx: Context) -> Table:
    """Return condition-level, per-temperature, per-seed, and joint claim rates and counts."""
    groups = defaultdict(list)
    for run in _runs(ctx):
        for temperature, seed in (
            (None, None),
            (run.temperature, None),
            (None, run.seed),
            (run.temperature, run.seed),
        ):
            groups[run.condition, temperature, seed].append(run)
    rows = []
    for (condition, temperature, seed), runs in groups.items():
        false = _false_share(runs)
        disagreement = _disagreement(runs)
        rows.append(
            {
                "condition": condition,
                "temperature": temperature,
                "seed": seed,
                "false_share": false.point,
                "false_ci_low": false.ci_low,
                "false_ci_high": false.ci_high,
                **false.details,
                "disagreement_rate": disagreement.point,
                "disagreement_ci_low": disagreement.ci_low,
                "disagreement_ci_high": disagreement.ci_high,
                **disagreement.details,
            }
        )
    return Table("srq3_breakdown", rows)


@table("srq3_examples")
def examples(ctx: Context) -> Table:
    """Return up to five distinct claims nearest truth 0.5, favoring disagreement on ties."""
    candidates = []
    for run in _runs(ctx):
        for result in run.checks:
            if result.crisp is not None and result.fuzzy is not None:
                distance = abs(result.fuzzy - FUZZY_TRUE_THRESHOLD)
                candidates.append((distance, run, result))

    rows = []
    seen = set()
    for distance, run, result in sorted(
        candidates, key=lambda item: (item[0], item[2].disagreement == "none")
    ):
        claim = result.claim
        identity = (claim.question_id, claim.quantifier, claim.summarizer, claim.restriction)
        if identity in seen:
            continue
        seen.add(identity)
        rows.append(
            {
                **run.question.model_dump(),
                "condition": run.condition,
                "temperature": run.temperature,
                "seed": run.seed,
                **claim.model_dump(
                    include={"slot", "text", "source", "quantifier", "summarizer", "restriction"}
                ),
                **result.model_dump(exclude={"claim", "reason"}),
                "distance_to_threshold": distance,
            }
        )
        if len(rows) == 5:
            break
    return Table("srq3_examples", rows)
