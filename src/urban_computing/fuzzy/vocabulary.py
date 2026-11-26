"""Linguistic vocabulary: membership functions from config/vocabulary.yaml (UC-020).

INTERFACE stub. Pure NumPy; no pandas/duckdb imports in this package.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

MembershipFn = Callable[[np.ndarray], np.ndarray]
"""Vectorised membership: array of attribute values -> array of degrees in [0, 1]."""


@dataclass(frozen=True)
class Trapezoid:
    """Trapezoid [a, b, c, d]; None = open shoulder (-inf for a/b, +inf for c/d)."""

    a: float | None
    b: float | None
    c: float | None
    d: float | None

    def __call__(self, x: np.ndarray) -> np.ndarray:
        raise NotImplementedError("UC-020")


@dataclass
class Vocabulary:
    summarizers: dict[str, dict[str, Trapezoid]] = field(default_factory=dict)
    quantifiers: dict[str, dict[str, Trapezoid]] = field(default_factory=dict)
    decision_words: tuple[str, ...] = ("safe", "at_risk", "risky")
    perception_spread_min: float = 2.0

    def late_for_my_transfer(self, margin_min: float) -> MembershipFn:
        """Membership of a delay (minutes) being too late for a transfer of `margin_min`."""
        raise NotImplementedError("UC-020")


def load_vocabulary(path: Path = Path("config/vocabulary.yaml")) -> Vocabulary:
    """Parse and validate the YAML vocabulary (raises ValueError on bad breakpoints)."""
    raise NotImplementedError("UC-020")
