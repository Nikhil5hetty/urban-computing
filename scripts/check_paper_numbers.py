#!/usr/bin/env python3
"""Invariant I6: every number in paper/ comes from results/results.json via paper/numbers.tex.

Fails (exit 1) if, in paper/**/*.tex outside paper/numbers.tex and paper/tables/, there is
- a digit sequence with a decimal point (`0.74`, `.5`, `3,5`), or
- a percentage (`52\\%`, `52 percent`, `52 per cent`).
LaTeX comments are ignored; escaped percent signs (`\\%`) are not comments. A number quoted
from cited literature is wrapped in `\\citednum{...}` (defined in main.tex) and skipped.
Plain integers (years, "3-minute rule", counts like "38 trains") are out of scope for the
checker and must be caught in review (paper/README.md).

    python3 scripts/check_paper_numbers.py            # checks paper/
    python3 scripts/check_paper_numbers.py --paper-dir some/dir
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER_DIR = ROOT / "paper"
ALLOWED_FILES = ("numbers.tex",)  # relative to the paper dir
ALLOWED_DIRS = ("tables",)
DECIMAL = re.compile(r"(?<![\w.])\d*[.,]\d+(?![\w])|(?<![\w.])\d+[.,]\d+")
PERCENT = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)?\s*(?:\\%|percent\b|per\s*cent\b)", re.IGNORECASE)
_COMMENT = re.compile(r"(?<!\\)%.*$")
_CITEDNUM = re.compile(r"\\citednum\{[^{}]*\}")


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    text: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.text}"


def _allowed(rel: Path) -> bool:
    return rel.as_posix() in ALLOWED_FILES or rel.parts[:1] in {(d,) for d in ALLOWED_DIRS}


def check(paper_dir: Path = PAPER_DIR) -> list[Violation]:
    """Every decimal number or percentage outside numbers.tex and tables/ (empty = I6 pass)."""
    out: list[Violation] = []
    for path in sorted(Path(paper_dir).rglob("*.tex")):
        rel = path.relative_to(paper_dir)
        if _allowed(rel):
            continue
        for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = _CITEDNUM.sub(" ", _COMMENT.sub("", raw))
            hits = {m.span(): m.group(0) for m in PERCENT.finditer(line)}
            for m in DECIMAL.finditer(line):  # a decimal inside a percentage is one hit
                if not any(a <= m.start() < b for a, b in hits):
                    hits[m.span()] = m.group(0)
            out.extend(Violation(path, i, text) for _, text in sorted(hits.items()))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--paper-dir", type=Path, default=PAPER_DIR)
    args = ap.parse_args(argv)
    violations = check(args.paper_dir)
    for v in violations:
        print(f"I6 violation: {v}", file=sys.stderr)
    status = "pass" if not violations else "FAIL"
    print(f"I6 {status}: {len(violations)} hard-coded number(s) (decimals or percentages)")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
