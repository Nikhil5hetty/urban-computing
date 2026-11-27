"""Ablations and sensitivity analyses (UC-054): which conclusions are robust?

Each ablation re-runs the affected registered experiments with a modified study config or a
modified vocabulary file. The code is never edited; the pre-registered settings stay the
reference. The output is not a hypothesis test: `ablations.csv` reports, per (ablation,
setting, hypothesis), the metric value and whether the verdict of the decision rule in
eval/hypotheses.yaml would change ("verdict_changes"). Runtimes go to a separate table,
`ablations_runtime.csv`, so that `ablations.csv` stays byte-identical across runs.

| Ablation | Settings | Override | Hypotheses re-run |
|---|---|---|---|
| tnorm | min | `mining.tnorm` (Q_c stays on `mining.qc_tnorm`, D-027) | H1a–H1c |
| beta | 0.5, 0.7 | `mining.beta` | H1a–H1c |
| coverage_r2 | 0.10, 0.20 | `mining.coverage_r2` (r1 unchanged, D-027) | H1a, H1c |
| delay_breakpoints | −1, +1 min | arrival-delay breakpoints shifted (vocabulary) | H1*, H3* |
| quantifiers | core+extended | `extended` words added to `core` (vocabulary) | H1*, H3* |
| min_transfer | 1, 3, 4 min | `connections.min_transfer_minutes_default` | H2a, H2b |
| crisp_late | official_ge_3 | `crisp_baseline.official_late`: "late" = delay ≥ 3 (D-007) | H3c |
| llm_temperature | each configured temperature | completions of that temperature only | H3a–H3c |

Runtime: one re-run of the affected experiments per setting, so the full table costs about
(number of settings) × (runtime of those experiments); `ablations_runtime.csv` records the
seconds per setting.
"""

from __future__ import annotations

import copy
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import yaml

from urban_computing.evaluation import registry
from urban_computing.evaluation.invariants import _i4_tables
from urban_computing.evaluation.registry import Context, Result, Table, table

SRQ1 = ("H1a", "H1b", "H1c")
SRQ2 = ("H2a", "H2b")
SRQ3 = ("H3a", "H3b", "H3c")
DELAY_ATTRIBUTE = "arrival_delay_minutes"


@dataclass(frozen=True)
class Ablation:
    """One setting: config overrides and/or a vocabulary edit, and the hypotheses to re-run."""

    name: str
    setting: str
    hypotheses: tuple[str, ...]
    overrides: dict[str, Any] | None = None
    vocab_edit: Callable[[dict], dict] | None = None
    temperature: float | None = None  # LLM ablation: keep completions of this temperature


def merge(base: dict, overrides: dict) -> dict:
    """Return a deep copy of `base` with `overrides` merged in (nested dicts recursively)."""
    out = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def shift_delay_breakpoints(minutes: float) -> Callable[[dict], dict]:
    """Vocabulary edit: shift every finite arrival-delay breakpoint by `minutes`."""

    def edit(vocab: dict) -> dict:
        out = copy.deepcopy(vocab)
        words = out["summarizers"][DELAY_ATTRIBUTE]
        for word, points in words.items():
            words[word] = [None if p is None else p + minutes for p in points]
        return out

    return edit


def with_extended_quantifiers(vocab: dict) -> dict:
    """Vocabulary edit: the `core` quantifier set also contains the `extended` words."""
    out = copy.deepcopy(vocab)
    out["quantifiers"]["core"] = {**out["quantifiers"]["core"], **out["quantifiers"]["extended"]}
    return out


def ablations(config: dict) -> list[Ablation]:
    """All ablation settings for this study config (settings equal to the default are skipped)."""
    mining, connections = config["mining"], config["connections"]
    out = [Ablation("tnorm", "min", SRQ1, {"mining": {"tnorm": "min"}})]
    out += [
        Ablation("beta", f"{b:g}", SRQ1, {"mining": {"beta": b}})
        for b in (0.5, 0.6, 0.7)
        if b != float(mining["beta"])
    ]
    out += [
        Ablation("coverage_r2", f"{r:g}", ("H1a", "H1c"), {"mining": {"coverage_r2": r}})
        for r in (0.10, 0.15, 0.20)
        if r != float(mining.get("coverage_r2", 0.15))
    ]
    out += [
        Ablation("delay_breakpoints", f"{d:+g}", SRQ1 + SRQ3, vocab_edit=shift_delay_breakpoints(d))
        for d in (-1, 1)
    ]
    out.append(
        Ablation("quantifiers", "core+extended", SRQ1 + SRQ3, vocab_edit=with_extended_quantifiers)
    )
    default = connections["min_transfer_minutes_default"]
    out += [
        Ablation(
            "min_transfer", f"{m:g}", SRQ2, {"connections": {"min_transfer_minutes_default": m}}
        )
        for m in connections["min_transfer_sensitivity"]
        if m != default
    ]
    out.append(
        Ablation("crisp_late", "official_ge_3", ("H3c",), {"crisp_baseline": {"official_late": 1}})
    )
    out += [
        Ablation("llm_temperature", f"{t:g}", SRQ3, temperature=float(t))
        for t in config["llm"]["temperatures"]
    ]
    return out


@contextmanager
def _context(base: Context, ablation: Ablation) -> Iterator[Context]:
    config = merge(base.config, ablation.overrides or {})
    paths = dict(base.paths)
    cache = {"i4_tables": _i4_tables(base)}  # the data tables do not depend on the ablation
    with TemporaryDirectory() as scratch:
        if ablation.vocab_edit is not None:
            source = Path(base.paths.get("vocabulary", "config/vocabulary.yaml"))
            vocab = ablation.vocab_edit(yaml.safe_load(source.read_text(encoding="utf-8")))
            target = Path(scratch) / "vocabulary.yaml"
            target.write_text(yaml.safe_dump(vocab, sort_keys=False), encoding="utf-8")
            paths["vocabulary"] = str(target)
        ctx = Context(config=config, sample=base.sample, paths=paths, seed=base.seed, cache=cache)
        if ablation.temperature is not None:
            ctx.cache["srq3_runs"] = _temperature_runs(base, ablation.temperature)
        yield ctx


def _temperature_runs(base: Context, temperature: float):
    from urban_computing.evaluation import srq3

    study = srq3._runs(base)
    return srq3._StudyRuns(
        [run for run in study.runs if run.temperature == temperature],
        [m for m in study.missing_primary_completions if m[1] == temperature],
    )


def _specs(config: dict) -> dict[str, dict]:
    path = Path(config["evaluation"]["hypotheses_file"])
    return {h["id"]: h for h in yaml.safe_load(path.read_text(encoding="utf-8"))["hypotheses"]}


def _metric(result: Result) -> float | None:
    return result.point if result.point is not None else result.value


def _baseline(ctx: Context) -> dict[str, Result]:
    if "ablation_baseline" not in ctx.cache:
        ctx.cache["ablation_baseline"] = {
            key: fn(ctx) for key, fn in sorted(registry.EXPERIMENTS.items())
        }
    return ctx.cache["ablation_baseline"]


def _rows(ctx: Context) -> tuple[list[dict], list[dict]]:
    if "ablation_rows" in ctx.cache:
        return ctx.cache["ablation_rows"]
    from urban_computing.evaluation.run import verdict

    specs = _specs(ctx.config)
    baseline = _baseline(ctx)
    rows, runtimes = [], []
    for ablation in ablations(ctx.config):
        started = time.perf_counter()
        with _context(ctx, ablation) as variant:
            for key in ablation.hypotheses:
                fn = registry.EXPERIMENTS.get(key)
                if fn is None or key not in specs or key not in baseline:
                    continue
                result = fn(variant)
                base_verdict = verdict(specs[key], baseline[key])
                new_verdict = verdict(specs[key], result)
                rows.append(
                    {
                        "ablation": ablation.name,
                        "setting": ablation.setting,
                        "hypothesis": key,
                        "metric": specs[key]["metric"],
                        "baseline_value": _metric(baseline[key]),
                        "value": _metric(result),
                        "baseline_verdict": base_verdict,
                        "verdict": new_verdict,
                        "verdict_changes": new_verdict != base_verdict,
                    }
                )
        runtimes.append(
            {
                "ablation": ablation.name,
                "setting": ablation.setting,
                "runtime_s": round(time.perf_counter() - started, 1),
            }
        )
    ctx.cache["ablation_rows"] = (rows, runtimes)
    return rows, runtimes


@table("ablations")
def ablation_table(ctx: Context) -> Table:
    """One row per (ablation, setting, hypothesis): metric, verdict and verdict_changes."""
    return Table("ablations", _rows(ctx)[0])


@table("ablations_runtime")
def runtime_table(ctx: Context) -> Table:
    """Seconds per ablation setting (kept apart so `ablations.csv` is deterministic)."""
    return Table("ablations_runtime", _rows(ctx)[1])
