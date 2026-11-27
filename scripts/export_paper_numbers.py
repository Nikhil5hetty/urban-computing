#!/usr/bin/env python3
"""Export results/results.json to paper/numbers.tex (LaTeX macros), then check I6.

    make paper-numbers                                     # results.json -> numbers.tex
    python3 scripts/export_paper_numbers.py --placeholder  # no results yet: macros = --

Macro names derive deterministically from ids: digits become words, so hypothesis `H1a`
gives `\\HoneaPoint`, `\\HoneaCILow`, `\\HoneaCIHigh`, `\\HoneaCI`, `\\HoneaP`, `\\HoneaValue`,
`\\HoneaVerdict`, and invariant `I3` gives `\\IthreeStatus`. Provenance: `\\ResultsGitSha`,
`\\ResultsConfigHash`, `\\ResultsSample`, `\\ResultsBanner` (a warning on synthetic results).

Also `\\CILevel` (e.g. "95\\%", from `evaluation.alpha` in config/study.yaml).

Formatting: point, CI and value with 2 decimals (integers without), p with 3 decimals or
"< 0.001"; missing values as "--". Nothing is written and the exit code is 2 if any
invariant failed, or if the results are real (not `meta.sample`) and any verdict is
`blocked_by_invariant`, i.e. a required invariant is missing or failed (docs/evaluation.md
§2.2). Sample results still export, with the red banner. After writing, I6
(scripts/check_paper_numbers.py) runs; its result is `\\IsixStatus`, a failure gives exit 1.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_paper_numbers  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "results.json"
OUT = ROOT / "paper" / "numbers.tex"
HYPOTHESES = ROOT / "eval" / "hypotheses.yaml"
CONFIG = ROOT / "config" / "study.yaml"
try:  # the runner's list of invariants required for real results (UC-053)
    from urban_computing.evaluation.run import _REAL_INVARIANTS as REQUIRED_REAL
except ImportError:  # pragma: no cover - package not installed
    REQUIRED_REAL = ("I1", "I2", "I3", "I4", "I5")

DIGITS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
FIELDS = (("point", "Point"), ("ci_low", "CILow"), ("ci_high", "CIHigh"), ("p", "P"),
          ("value", "Value"))  # fmt: skip
VERDICTS = {
    "supported": "supported",
    "not_supported": "not supported",
    "inconclusive": "inconclusive",
    "not_run": "not run",
    "blocked_by_invariant": "blocked by invariant",
}
MISSING = "--"


def macro_base(identifier: str) -> str:
    """`H1a` -> `Honea`, `I6` -> `Isix`: digits spelled out, letters kept (TeX-safe)."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", identifier):
        raise ValueError(f"id {identifier!r} cannot become a LaTeX macro name")
    return "".join(DIGITS[int(ch)] if ch.isdigit() else ch for ch in identifier)


def fmt(x: Any, kind: str = "num") -> str:
    """Number -> paper text. kind: 'num' (2 decimals, integers as is) or 'p' (3 decimals)."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return MISSING
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError(f"not a number: {x!r}")
    if kind == "p":
        return "$<$ 0.001" if x < 0.001 else f"{x:.3f}"
    if float(x).is_integer() and abs(x) >= 1:
        return str(int(x))
    return f"{x:.2f}"


def _tex_escape(text: str) -> str:
    return re.sub(r"([&%$#_{}])", r"\\\1", text)


def _def(name: str, body: str) -> str:
    return f"\\newcommand{{\\{name}}}{{{body}}}"


def _check_exportable(results: Mapping[str, Any]) -> None:
    """Raise RuntimeError if the numbers may not reach the paper (docs/evaluation.md §2.2)."""
    invariants = results.get("invariants") or {}
    failed = sorted(k for k, v in invariants.items() if v == "fail")
    if failed:
        raise RuntimeError(f"invariant(s) failed: {', '.join(failed)}; numbers not exported")
    if (results.get("meta") or {}).get("sample"):
        return  # synthetic results: exported with the red banner
    hyps = results.get("hypotheses") or {}
    blocked = sorted(k for k, h in hyps.items() if h.get("verdict") == "blocked_by_invariant")
    if blocked:
        not_passing = [f"{i} ({invariants.get(i, 'missing')})" for i in REQUIRED_REAL
                       if invariants.get(i) != "pass"]  # fmt: skip
        raise RuntimeError(
            f"real results with verdicts blocked by invariants ({', '.join(blocked)}); "
            f"required invariants not passing: {', '.join(not_passing) or 'see REPORT.md'}; "
            "numbers not exported"
        )


def render(
    results: Mapping[str, Any], source: str = "results/results.json", alpha: float = 0.05
) -> str:
    """LaTeX source of numbers.tex for a parsed results.json (pure; deterministic).

    `alpha` (config `evaluation.alpha`) gives `\\CILevel`. Raises RuntimeError when the
    results may not be exported (see `_check_exportable`).
    """
    _check_exportable(results)
    invariants = results.get("invariants") or {}
    meta = results.get("meta") or {}
    lines = [
        "% GENERATED by scripts/export_paper_numbers.py - do not edit (invariant I6).",
        f"% source: {source}; git {meta.get('git_sha', '?')}; "
        f"config {meta.get('config_hash', '?')}",
        "% Every number in paper/ must come from a macro defined here.",
        "",
    ]
    for hid in sorted(results.get("hypotheses") or {}):
        h = results["hypotheses"][hid]
        base = macro_base(hid)
        for key, suffix in FIELDS:
            lines.append(_def(f"{base}{suffix}", fmt(h.get(key), "p" if key == "p" else "num")))
        lo, hi = fmt(h.get("ci_low")), fmt(h.get("ci_high"))
        lines.append(_def(f"{base}CI", MISSING if MISSING in (lo, hi) else f"[{lo}, {hi}]"))
        verdict = h.get("verdict") or "not_run"
        lines.append(_def(f"{base}Verdict", VERDICTS.get(verdict, _tex_escape(str(verdict)))))
        lines.append("")
    for iid in sorted(invariants):
        if iid != "I6":
            lines.append(_def(f"{macro_base(iid)}Status", _tex_escape(str(invariants[iid]))))
    sample = bool(meta.get("sample"))
    lines += [
        "",
        _def("ResultsGitSha", _tex_escape(str(meta.get("git_sha") or MISSING)[:7])),
        _def("ResultsConfigHash", _tex_escape(str(meta.get("config_hash") or MISSING)[:12])),
        _def("ResultsSample", "yes" if sample else "no"),
        _def("CILevel", f"{fmt(round(100 * (1 - alpha), 6))}\\%"),
        _def(
            "ResultsBanner",
            r"\textcolor{red}{\textbf{Synthetic sample results (make eval-sample): "
            r"not for submission.}}"
            if sample
            else "",
        ),
    ]
    return "\n".join(lines) + "\n"


def placeholder_results(hypotheses_file: Path = HYPOTHESES) -> dict[str, Any]:
    """results.json-shaped dict with every hypothesis and invariant id and no values."""
    import yaml

    spec = yaml.safe_load(hypotheses_file.read_text(encoding="utf-8"))
    return {
        "hypotheses": {h["id"]: {"verdict": "not_run"} for h in spec["hypotheses"]},
        "invariants": {i["id"]: "not run" for i in spec["invariants"]},
        "meta": {"sample": True, "git_sha": None, "config_hash": None},
    }


def export(
    results_path: Path, out_path: Path, *, placeholder: bool = False, config_path: Path = CONFIG
) -> int:
    """Write numbers.tex and run I6. Returns the exit code (0 ok, 1 I6, 2 not exportable)."""
    import yaml

    alpha = float(yaml.safe_load(config_path.read_text(encoding="utf-8"))["evaluation"]["alpha"])
    if placeholder:
        results, source = placeholder_results(), "placeholder (no results.json)"
    else:
        if not results_path.exists():
            print(f"{results_path} missing: run `make eval` (or `make eval-sample`) first, "
                  "or use --placeholder", file=sys.stderr)  # fmt: skip
            return 2
        results, source = json.loads(results_path.read_text(encoding="utf-8")), str(results_path)
    try:
        text = render(results, source if placeholder else "results/results.json", alpha=alpha)
    except RuntimeError as e:
        print(f"not exported: {e}", file=sys.stderr)
        return 2
    violations = check_paper_numbers.check(out_path.parent)
    text += _def("IsixStatus", "pass" if not violations else "fail") + "\n"
    out_path.write_text(text, encoding="utf-8")
    print(f"wrote {out_path} ({text.count(chr(92) + 'newcommand')} macros)")
    for v in violations:
        print(f"I6 violation: {v}", file=sys.stderr)
    print(f"I6 {'pass' if not violations else 'FAIL'}")
    return 1 if violations else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--results", type=Path, default=RESULTS)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--placeholder", action="store_true", help="macros = -- (no results yet)")
    ap.add_argument("--config", type=Path, default=CONFIG, help="study config (CI level)")
    args = ap.parse_args(argv)
    return export(args.results, args.out, placeholder=args.placeholder, config_path=args.config)


if __name__ == "__main__":
    sys.exit(main())
