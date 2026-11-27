"""Compare UC-032 and UC-031 decision words on the fixed UC-033 question cells."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from urban_computing.assistant.contract import Answer, Question
from urban_computing.assistant.engine import CAUTION, VOCAB_PATH, NoDataError, answer, hub_arrivals
from urban_computing.evaluation.invariants import _i4_tables
from urban_computing.evaluation.registry import Context, Result, Table, experiment, table
from urban_computing.evaluation.stats import fisher_exact, wilson_ci
from urban_computing.fuzzy.vocabulary import load_vocabulary


@dataclass
class _Comparisons:
    n_questions: int = 0
    n_cells: int = 0
    missing_questions: bool = False
    answers: list[Answer] = field(default_factory=list)
    excluded: dict[str, int] = field(
        default_factory=lambda: {"no_fuzzy_verdict": 0, "no_crisp_verdict": 0}
    )
    sensitivity_flips: dict[float, int] = field(default_factory=dict)


def _cell_key(q: Question) -> tuple:
    # Match the selector precedence in connection_segment and the crisp baseline.
    arriving = ("line", q.arr_line) if q.arr_line else ("product", q.arr_product)
    departing = ("line", q.dep_line) if q.dep_line else ("product", q.dep_product or None)
    return q.hub, arriving, departing, q.time_band, q.weekday_group, q.margin_min


def _flipped(ans: Answer) -> bool:
    return ans.crisp_decision != ans.decision


def _compare(ctx: Context) -> _Comparisons:
    path = Path(ctx.config["evaluation"].get("questions_file", "eval/questions.jsonl"))
    result = _Comparisons()
    settings = ctx.config["connections"]
    result.sensitivity_flips = dict.fromkeys(settings["min_transfer_sensitivity"], 0)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as error:
        if not ctx.sample:
            raise FileNotFoundError(
                f"SRQ2 requires {path}. Generate it with `make questions`."
            ) from error
        result.missing_questions = True
        return result

    cells = {}
    for line in lines:
        if line.strip():
            question = Question.model_validate_json(line, context={"study_config": ctx.config})
            result.n_questions += 1
            cells.setdefault(_cell_key(question), question)
    result.n_cells = len(cells)
    if not cells:
        raise ValueError(f"SRQ2 question set is empty: {path}")

    arrivals, connections, hub_ids = _i4_tables(ctx)
    settings = {**settings}
    if hub_ids and not settings.get("hub_stop_ids"):
        settings["hub_stop_ids"] = hub_ids
    vocab_path = ctx.paths.get("vocabulary", VOCAB_PATH)
    vocab = load_vocabulary(Path(vocab_path))
    config = {
        **ctx.config,
        "connections": settings,
        "paths": {**ctx.config.get("paths", {}), "vocabulary": str(vocab_path)},
    }
    default = settings["min_transfer_minutes_default"]
    variants = {
        minutes: {**config, "connections": {**settings, "min_transfer_minutes_default": minutes}}
        for minutes in result.sensitivity_flips
        if minutes != default
    }
    hubs = {}
    for question in cells.values():
        if question.hub not in hubs:
            hubs[question.hub] = (
                connections.loc[connections["hub"] == question.hub],
                hub_arrivals(question, arrivals, config),
            )
        pairs, hub_rows = hubs[question.hub]
        try:
            baseline = answer(question, pairs, hub_rows, vocab, config)
        except NoDataError:
            result.excluded["no_fuzzy_verdict"] += 1
            continue
        if baseline.crisp_decision is None:
            result.excluded["no_crisp_verdict"] += 1
            continue
        result.answers.append(baseline)

        for minutes in result.sensitivity_flips:
            # UC-031's arrival-only fallback is independent of minimum transfer time.
            variant = baseline
            if minutes in variants and not baseline.provenance.fallback:
                variant = answer(question, pairs, hub_rows, vocab, variants[minutes])
            result.sensitivity_flips[minutes] += baseline.crisp_decision != variant.decision
    return result


def _comparisons(ctx: Context) -> _Comparisons:
    if "srq2" not in ctx.cache:
        ctx.cache["srq2"] = _compare(ctx)
    return ctx.cache["srq2"]


@experiment("H2a")
def h2a(ctx: Context) -> Result:
    """Return the flip proportion with a 95% Wilson interval and cell counts by word pair."""
    comparison = _comparisons(ctx)
    matrix = {crisp: dict.fromkeys(CAUTION, 0) for crisp in CAUTION}
    for ans in comparison.answers:
        matrix[ans.crisp_decision][ans.decision] += 1
    n = len(comparison.answers)
    flips = sum(map(_flipped, comparison.answers))
    point, low, high = wilson_ci(flips, n) if n else (None, None, None)
    details = {
        "n_questions": comparison.n_questions,
        "n_cells": comparison.n_cells,
        "n_compared": n,
        "n_flips": flips,
        "n_fallback": sum(ans.provenance.fallback for ans in comparison.answers),
        "excluded": comparison.excluded,
        "flip_matrix": matrix,
    }
    if comparison.missing_questions:
        details["reason"] = "missing_question_set"
    return Result(point=point, ci_low=low, ci_high=high, details=details)


def _margin_counts(answers: list[Answer]) -> dict:
    n = len(answers)
    flips = sum(map(_flipped, answers))
    return {"n": n, "n_flips": flips, "flip_rate": flips / n if n else None}


@experiment("H2b")
def h2b(ctx: Context) -> Result:
    """Return short (≤4 min) minus long (≥6 min) flip proportions and two-sided Fisher p."""
    answers = _comparisons(ctx).answers
    short = _margin_counts([ans for ans in answers if ans.question.margin_min <= 4])
    long = _margin_counts([ans for ans in answers if ans.question.margin_min >= 6])
    details = {"short": short, "long": long, "n_between": len(answers) - short["n"] - long["n"]}
    if not short["n"] or not long["n"]:
        return Result(details=details)
    counts = [[group["n_flips"], group["n"] - group["n_flips"]] for group in (short, long)]
    return Result(
        point=short["flip_rate"] - long["flip_rate"], p=fisher_exact(counts), details=details
    )


@table("srq2_transfer_sensitivity")
def transfer_sensitivity(ctx: Context) -> Table:
    """Return the flip proportion for each configured minimum transfer time in minutes."""
    comparison = _comparisons(ctx)
    n = len(comparison.answers)
    rows = [
        {
            "min_transfer_minutes": minutes,
            "n": n,
            "n_flips": flips,
            "flip_rate": flips / n if n else None,
        }
        for minutes, flips in comparison.sensitivity_flips.items()
    ]
    return Table("srq2_transfer_sensitivity", rows)


@table("srq2_examples")
def examples(ctx: Context) -> Table:
    """Return up to three flipped cells in file order, with their original explanations."""
    rows = []
    for ans in [ans for ans in _comparisons(ctx).answers if _flipped(ans)][:3]:
        q = ans.question
        own = ans.explanations[0]  # UC-031 always explains the passenger's decision first.
        crisp_word = ans.crisp_decision.replace("_", " ")
        fuzzy_word = ans.decision.replace("_", " ")
        rows.append(
            {
                **q.model_dump(),
                "crisp_decision": ans.crisp_decision,
                "fuzzy_decision": ans.decision,
                "fallback": ans.provenance.fallback,
                "explanation": own.sentence,
                "truth": own.truth,
                "n": own.n,
                "text": (
                    f"The official punctuality view rates this trip {crisp_word}. "
                    f"For your {q.margin_min:g}-minute transfer at {q.hub}, the verdict is "
                    f"{fuzzy_word}. {own.sentence}"
                ),
            }
        )
    return Table("srq2_examples", rows)
