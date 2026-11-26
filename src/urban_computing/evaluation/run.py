"""Run registered evaluations and write the JSON report, Markdown report and CSV tables."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import math
import operator
import platform
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from importlib import import_module, metadata
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np
import yaml

from urban_computing.evaluation import registry
from urban_computing.evaluation.registry import Context, InvariantResult, Result

_COMPARISONS = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}
_FIELDS = ("point", "ci_low", "ci_high", "p", "value")
_INVARIANT_MODULE = "urban_computing.evaluation.invariants"
_SAMPLE_INVARIANTS = ("I1", "I2", "I4", "I5")
_REAL_INVARIANTS = ("I1", "I2", "I3", "I4", "I5")


def _operand(node: ast.expr, values: Result) -> float | None:
    if isinstance(node, ast.Name) and node.id in _FIELDS:
        return getattr(values, node.id)
    sign = 1
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        sign = -1 if isinstance(node.op, ast.USub) else 1
        node = node.operand
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return sign * node.value
    raise ValueError(f"Unsupported verdict operand {ast.unparse(node)!r}")


def _rule(node: ast.expr, values: Result) -> bool:
    if isinstance(node, ast.BoolOp):
        matches = [_rule(child, values) for child in node.values]
        return all(matches) if isinstance(node.op, ast.And) else any(matches)
    if isinstance(node, ast.Compare):
        operands = [_operand(child, values) for child in (node.left, *node.comparators)]
        matches = []
        for op, left, right in zip(node.ops, operands[:-1], operands[1:], strict=True):
            compare = _COMPARISONS.get(type(op))
            if compare is None:
                raise ValueError(f"Unsupported verdict comparison {type(op).__name__}")
            matches.append(
                left is not None
                and right is not None
                and math.isfinite(left)
                and math.isfinite(right)
                and compare(left, right)
            )
        return all(matches)
    raise ValueError(f"Unsupported verdict expression {ast.unparse(node)!r}")


def verdict(spec: dict, result: Result) -> str:
    """Apply the two preregistered comparison expressions to a hypothesis result."""
    supported = _rule(ast.parse(spec["supported_if"], mode="eval").body, result)
    rejected = _rule(ast.parse(spec["not_supported_if"], mode="eval").body, result)
    if supported and rejected:
        raise ValueError(f"Conflicting verdict rules for {spec['id']}")
    if supported:
        return "supported"
    return "not_supported" if rejected else "inconclusive"


def _modules(only: str | None) -> set[str]:
    names = registry.EXPERIMENT_MODULES
    selected = names
    if only is not None:
        selected = tuple(name for name in names if only in (name, name.rsplit(".", 1)[-1]))
        if not selected:
            raise ValueError(f"Unknown evaluation module {only!r}")
    loaded = set()
    for name in names:
        if name not in selected and name != _INVARIANT_MODULE:
            continue
        try:
            import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name != name:
                raise
        else:
            if name in selected:
                loaded.add(name)
    return loaded


def _analytical_truth(ctx: Context) -> InvariantResult:
    from urban_computing.fuzzy.truth import truth_restricted, truth_simple
    from urban_computing.fuzzy.vocabulary import load_vocabulary

    vocab = load_vocabulary(Path(ctx.paths["vocabulary"]))
    core = vocab.quantifiers["core"]
    most = core["most"]
    cases = [
        (np.zeros(5), most, 0.0),
        (np.ones(5), most, 1.0),
        (np.array([1, 1, 1, 1, 0]), most, (0.8 - 0.5) / (0.85 - 0.5)),
        (np.full(5, 0.5), core["about_half"], 1.0),
    ]
    errors = [abs(truth_simple(mu, q) - expected) for mu, q, expected in cases]
    observed = truth_restricted(
        np.array([1, 1, 1, 1, 0]),
        np.array([1, 1, 1, 0, 1]),
        most,
        ctx.config["mining"]["tnorm"],
    )
    errors.append(abs(observed - (0.75 - 0.5) / (0.85 - 0.5)))
    return InvariantResult(all(error < 1e-9 for error in errors), {"errors": errors})


def _simpful_memberships(ctx: Context) -> InvariantResult:
    from simpful import Trapezoidal_MF

    from urban_computing.fuzzy.vocabulary import load_vocabulary

    vocab = load_vocabulary(Path(ctx.paths["vocabulary"]))
    errors = {}
    for groups, bounds in ((vocab.summarizers, (-5, 30)), (vocab.quantifiers, (0, 1))):
        grid = np.linspace(*bounds, 10_000)
        for group, words in groups.items():
            for word, fn in words.items():
                a, b, c, d = fn.a, fn.b, fn.c, fn.d
                if a is None:
                    a = b = c
                if c is None:
                    c = d = b
                reference = Trapezoidal_MF(a=a, b=b, c=c, d=d)
                expected = [reference(float(x)) for x in grid]
                errors[f"{group}.{word}"] = float(np.max(np.abs(fn(grid) - expected)))
    return InvariantResult(all(error < 1e-6 for error in errors.values()), errors)


def _manifest(ctx: Context) -> InvariantResult:
    from urban_computing.data.download import verify_manifest

    path = Path(ctx.paths["manifest"])
    try:
        mismatches = verify_manifest(path)
    except FileNotFoundError:
        return InvariantResult(False, {"missing_manifest": str(path)})
    return InvariantResult(not mismatches, {"mismatches": mismatches})


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _provenance(config_bytes: bytes, sample: bool) -> dict:
    git = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    packages = ("numpy", "scipy", "statsmodels", "pandas", "duckdb", "pyarrow", "simpful", "pyyaml")
    return {
        "git_sha": git.stdout.strip() or None,
        "config_hash": hashlib.sha256(config_bytes).hexdigest(),
        "versions": {
            "python": platform.python_version(),
            **{name: metadata.version(name) for name in packages},
        },
        "sample": sample,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def _write_table(table: registry.Table, out: Path) -> None:
    columns = list(dict.fromkeys(key for row in table.rows for key in row))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as stream:
        if columns:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(table.rows)


def _evaluate(ctx: Context, specs: dict, only: str | None, out: Path) -> tuple[dict, str]:
    loaded = _modules(only)

    def selected(fn: Any) -> bool:
        return only is None or fn.__module__ in loaded

    required = _SAMPLE_INVARIANTS if ctx.sample else _REAL_INVARIANTS
    gates = {"I1": _analytical_truth, "I2": _simpful_memberships, "I3": _manifest}
    gates.update(registry.INVARIANTS)
    invariants, failures, missing = {}, {}, []
    for key in required:
        if key not in gates:
            missing.append(key)
            continue
        result = gates[key](ctx)
        invariants[key] = "pass" if result.passed else "fail"
        if not result.passed:
            failures[key] = result.details

    hypotheses = {}
    for spec in specs["hypotheses"]:
        key = spec["id"]
        fn = registry.EXPERIMENTS.get(key)
        result = fn(ctx) if fn is not None and selected(fn) else None
        if result is None:
            outcome = "not_run"
            result = Result()
        else:
            outcome = "blocked_by_invariant" if failures or missing else verdict(spec, result)
        hypotheses[key] = {**asdict(result), "verdict": outcome}

    tables = {}
    for _, fn in sorted(registry.TABLES.items()):
        if selected(fn):
            table = fn(ctx)
            if Path(table.name).name != table.name or table.name in ("", ".", ".."):
                raise ValueError(f"Invalid table name {table.name!r}")
            relative = Path("tables") / f"{table.name}.csv"
            _write_table(table, out / relative)
            tables[table.name] = relative.as_posix()

    lines = [f"# Project evaluation ({'sample' if ctx.sample else 'real data'})"]
    if failures:
        lines.extend(["", "## Invariant failures", ""])
        lines.extend(f"- {key} failed. {details}" for key, details in failures.items())
    if missing:
        lines.extend(["", f"## Required invariants not run: {', '.join(missing)}"])
    if failures or missing:
        lines.append("\nHypothesis verdicts are blocked.")
    lines.extend(["", "## Invariants", ""])
    lines.extend(f"- {key} {status}" for key, status in invariants.items())
    if ctx.sample:
        lines.append("- I3 is required only for real data.")
    lines.append("- I6 is checked by the paper export (UC-070).")
    lines.extend(["", "## Hypotheses", ""])
    if only:
        lines.append(f"Selected module `{only}`.\n")
    for key, result in hypotheses.items():
        metrics = ", ".join(
            f"{field} {result[field]:.6g}"
            for field in _FIELDS
            if result[field] is not None and math.isfinite(result[field])
        )
        suffix = f" ({metrics})" if metrics else ""
        lines.append(f"- {key} {result['verdict']}{suffix}")
    return {"hypotheses": hypotheses, "invariants": invariants, "tables": tables}, "\n".join(lines)


def run(config_path: Path, *, sample: bool = False, only: str | None = None) -> dict:
    """Evaluate the study config and return the results written to results/results.json."""
    config_bytes = config_path.read_bytes()
    config = yaml.safe_load(config_bytes)
    hypothesis_path = Path(config["evaluation"]["hypotheses_file"])
    specs = yaml.safe_load(hypothesis_path.read_text(encoding="utf-8"))
    out = Path("results")
    data = config["data"]
    fixtures = Path("tests/fixtures/ist_sample")
    with TemporaryDirectory() as scratch:
        interim = Path(scratch) / "interim" if sample else Path(data["interim_dir"])
        processed = Path(scratch) / "processed" if sample else Path(data["processed_dir"])
        paths = {
            "raw_dir": str(fixtures) if sample else data["raw_dir"],
            "service_points_dir": str(fixtures) if sample else data["service_points_dir"],
            "interim_dir": str(interim),
            "processed_dir": str(processed),
            "arrivals": str(processed / "arrivals.parquet"),
            "connections": str(processed / "connections.parquet"),
            "vocabulary": "config/vocabulary.yaml",
            "results_dir": str(out),
        }
        if sample:
            interim.mkdir()
            processed.mkdir()
            paths["ground_truth"] = str(fixtures / "ground_truth.json")
        else:
            paths["manifest"] = "data/MANIFEST.json"
        ctx = Context(config=config, sample=sample, paths=paths, seed=config["study"]["seed"])
        results, report = _evaluate(ctx, specs, only, out)
    results["meta"] = _provenance(config_bytes, sample)
    results = _json_safe(results)
    out.mkdir(exist_ok=True)
    (out / "results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    versions = results["meta"]["versions"]
    report += "\n\n## Library versions\n\n" + "\n".join(
        f"- {name} {version}" for name, version in sorted(versions.items())
    )
    (out / "REPORT.md").write_text(report + "\n", encoding="utf-8")
    return results


def main() -> None:
    """Parse CLI options and write the evaluation artifacts under results/."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--only", metavar="MODULE")
    args = parser.parse_args()
    run(args.config, sample=args.sample, only=args.only)


if __name__ == "__main__":
    main()
