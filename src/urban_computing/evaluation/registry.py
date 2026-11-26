"""Experiment / invariant registry — the frozen INTERFACE between experiment tickets
(UC-024, UC-050..UC-054, invariants in data/fuzzy/assistant tickets) and the project
runner (UC-053).

An experiment module registers functions at import time:

    from urban_computing.evaluation.registry import Context, Result, experiment

    @experiment("H1a")
    def h1a(ctx: Context) -> Result:
        ...
        return Result(point=0.14, ci_low=0.11, ci_high=0.17)

The runner imports every module listed in EXPERIMENT_MODULES (missing modules are skipped,
so hypotheses whose ticket is not merged get verdict "not_run").
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

EXPERIMENT_MODULES = (
    "urban_computing.evaluation.invariants",  # I1..I6 wrappers (UC-053)
    "urban_computing.evaluation.baseline",  # UC-024 (table only, no hypothesis)
    "urban_computing.evaluation.srq1",  # UC-050: H1a H1b H1c
    "urban_computing.evaluation.srq2",  # UC-051: H2a H2b
    "urban_computing.evaluation.srq3",  # UC-052: H3a H3b H3c
    "urban_computing.evaluation.ablations",  # UC-054 (tables only)
)


@dataclass
class Context:
    """Everything an experiment may read. Experiments must not read files themselves
    except through `paths`; `cache` lets experiments share loaded tables."""

    config: dict
    sample: bool  # True for `make eval-sample` (synthetic fixture)
    paths: dict[str, str]
    seed: int
    cache: dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    """Fields match the expressions allowed in eval/hypotheses.yaml decision rules."""

    point: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    p: float | None = None
    value: float | None = None  # counts (e.g. H1b)
    details: dict[str, Any] = field(default_factory=dict)  # tables, examples, n


@dataclass
class InvariantResult:
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Table:
    """Non-hypothesis outputs (baseline, ablations) written to results/tables/<name>.csv."""

    name: str
    rows: list[dict[str, Any]]


EXPERIMENTS: dict[str, Callable[[Context], Result]] = {}
INVARIANTS: dict[str, Callable[[Context], InvariantResult]] = {}
TABLES: dict[str, Callable[[Context], Table]] = {}


def _register(store: dict, key: str) -> Callable:
    def deco(fn: Callable) -> Callable:
        if key in store and store[key] is not fn:
            raise ValueError(f"{key} registered twice ({store[key].__module__}, {fn.__module__})")
        store[key] = fn
        return fn

    return deco


def experiment(hypothesis_id: str) -> Callable:
    """Register a function computing one hypothesis (id as in eval/hypotheses.yaml)."""
    return _register(EXPERIMENTS, hypothesis_id)


def invariant(invariant_id: str) -> Callable:
    """Register a correctness gate I1..I6."""
    return _register(INVARIANTS, invariant_id)


def table(name: str) -> Callable:
    """Register a table producer (baseline, ablations, srq examples)."""
    return _register(TABLES, name)
