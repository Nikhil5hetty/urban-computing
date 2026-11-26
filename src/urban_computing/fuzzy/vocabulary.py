"""Linguistic vocabulary: membership functions from config/vocabulary.yaml (UC-020).

Pure NumPy; no pandas/duckdb imports in this package. The only I/O is the thin
`load_vocabulary` reader; all parsing and validation is in `vocabulary_from_dict`.
Breakpoints and their justification: docs/methods.md §1.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

MembershipFn = Callable[[np.ndarray], np.ndarray]
"""Vectorised membership: array of attribute values -> array of degrees in [0, 1]."""


def _bound(v: float | None, default: float) -> float:
    return default if v is None else float(v)


@dataclass(frozen=True)
class Trapezoid:
    """Trapezoid [a, b, c, d]; None = open shoulder (-inf for a/b, +inf for c/d).

    Membership rises linearly from 0 at `a` to 1 at `b`, is 1 on [b, c] and falls linearly
    to 0 at `d`. Triangles (b == c) and vertical edges (a == b or c == d, i.e. crisp steps)
    are allowed. A left shoulder needs both `a` and `b` None, a right shoulder both `c` and
    `d` None. Raises ValueError on NaN, half-open shoulders, unordered breakpoints, or all
    four None (constant 1 is not a word).
    """

    a: float | None
    b: float | None
    c: float | None
    d: float | None

    def __post_init__(self) -> None:
        vals = (self.a, self.b, self.c, self.d)
        if any(v is not None and math.isnan(float(v)) for v in vals):
            raise ValueError(f"breakpoint is NaN: {vals}")
        if (self.a is None) != (self.b is None):
            raise ValueError(f"left shoulder needs both a and b null: {vals}")
        if (self.c is None) != (self.d is None):
            raise ValueError(f"right shoulder needs both c and d null: {vals}")
        if all(v is None for v in vals):
            raise ValueError("all breakpoints null: membership would be constant 1")
        a, b = _bound(self.a, -math.inf), _bound(self.b, -math.inf)
        c, d = _bound(self.c, math.inf), _bound(self.d, math.inf)
        if not a <= b <= c <= d:
            raise ValueError(f"breakpoints must satisfy a <= b <= c <= d: {vals}")

    def __call__(self, x: np.ndarray) -> np.ndarray:
        """Membership degrees of `x` (any shape, attribute units) as float64 in [0, 1].

        NaN in `x` gives NaN (missing values are not silently counted as non-members).
        """
        x = np.asarray(x, dtype=np.float64)
        a, b = _bound(self.a, -math.inf), _bound(self.b, -math.inf)
        c, d = _bound(self.c, math.inf), _bound(self.d, math.inf)
        out = np.zeros_like(x)
        with np.errstate(invalid="ignore", divide="ignore"):
            rising = (x > a) & (x < b)
            falling = (x > c) & (x < d)
            out = np.where(rising, (x - a) / (b - a), out)
            out = np.where(falling, (d - x) / (d - c), out)
        out = np.where((x >= b) & (x <= c), 1.0, out)  # core last: wins at vertical edges
        return np.where(np.isnan(x), np.nan, out)


@dataclass
class Vocabulary:
    """Parsed vocabulary.

    summarizers[attribute][word] and quantifiers[set][word] are Trapezoids; summarizers are
    in the attribute's units (minutes), quantifiers on proportions in [0, 1].
    """

    summarizers: dict[str, dict[str, Trapezoid]] = field(default_factory=dict)
    quantifiers: dict[str, dict[str, Trapezoid]] = field(default_factory=dict)
    decision_words: tuple[str, ...] = ("safe", "at_risk", "risky")
    perception_spread_min: float = 2.0

    def late_for_my_transfer(
        self, margin_min: float, spread_min: float | None = None
    ) -> MembershipFn:
        """Membership of a delay (minutes) being too late for a transfer of `margin_min`.

        0 for delay <= margin - spread, 1 for delay >= margin, linear in between
        (monotone). `spread_min` defaults to `perception_spread_min`; 0 gives the crisp
        step "delay >= margin". Raises ValueError for a negative or NaN spread/margin.
        """
        spread = self.perception_spread_min if spread_min is None else float(spread_min)
        margin = float(margin_min)
        if math.isnan(margin) or math.isnan(spread) or spread < 0:
            raise ValueError(f"need finite margin and spread >= 0, got {margin}, {spread}")
        return Trapezoid(margin - spread, margin, None, None)


def _words(group: Any, where: str, unit_interval: bool) -> dict[str, Trapezoid]:
    if not isinstance(group, Mapping) or not group:
        raise ValueError(f"{where}: expected a non-empty mapping of word -> [a, b, c, d]")
    out: dict[str, Trapezoid] = {}
    for word, abcd in group.items():
        if not isinstance(abcd, (list, tuple)) or len(abcd) != 4:
            raise ValueError(f"{where}.{word}: expected [a, b, c, d], got {abcd!r}")
        try:
            vals = [None if v is None else float(v) for v in abcd]
            trap = Trapezoid(*vals)
        except (TypeError, ValueError) as e:
            raise ValueError(f"{where}.{word}: {e}") from e
        if unit_interval and any(v is not None and not 0.0 <= v <= 1.0 for v in vals):
            raise ValueError(f"{where}.{word}: quantifier breakpoints must lie in [0, 1]")
        out[str(word)] = trap
    return out


def vocabulary_from_dict(cfg: Mapping[str, Any]) -> Vocabulary:
    """Build a Vocabulary from the parsed YAML mapping (schema: config/vocabulary.yaml).

    Raises ValueError with the offending key on missing sections, malformed or unordered
    breakpoints, quantifier breakpoints outside [0, 1], empty decision words or a
    negative perception spread.
    """
    if not isinstance(cfg, Mapping):
        raise ValueError("vocabulary config must be a mapping")
    for key in ("summarizers", "quantifiers"):
        if not isinstance(cfg.get(key), Mapping) or not cfg[key]:
            raise ValueError(f"missing or empty section `{key}`")
    summ = {
        str(attr): _words(g, f"summarizers.{attr}", False) for attr, g in cfg["summarizers"].items()
    }
    quant = {str(s): _words(g, f"quantifiers.{s}", True) for s, g in cfg["quantifiers"].items()}

    words = cfg.get("decision_words", list(Vocabulary.decision_words))
    if not isinstance(words, (list, tuple)) or not words or len(set(words)) != len(words):
        raise ValueError(f"decision_words must be a non-empty list of unique words: {words!r}")

    spread = ((cfg.get("perception") or {}).get("late_for_my_transfer") or {}).get("spread_minutes")
    spread = Vocabulary.perception_spread_min if spread is None else spread
    try:
        spread = float(spread)
    except (TypeError, ValueError) as e:
        raise ValueError(f"perception spread_minutes is not a number: {spread!r}") from e
    if math.isnan(spread) or spread < 0:
        raise ValueError(f"perception spread_minutes must be >= 0, got {spread}")

    return Vocabulary(
        summarizers=summ,
        quantifiers=quant,
        decision_words=tuple(str(w) for w in words),
        perception_spread_min=spread,
    )


def load_vocabulary(path: Path = Path("config/vocabulary.yaml")) -> Vocabulary:
    """Read the YAML file at `path` and parse it with `vocabulary_from_dict`.

    Raises ValueError on bad breakpoints (see `vocabulary_from_dict`).
    """
    import yaml

    return vocabulary_from_dict(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
