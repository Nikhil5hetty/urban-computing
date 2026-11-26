"""Hudec quality measures (UC-022). INTERFACE stub. Formulas: docs/methods.md §3."""

from __future__ import annotations

import numpy as np


def coverage(mu_R: np.ndarray | None, mu_S: np.ndarray, params: dict | None = None) -> float:
    """Degree of sufficient coverage C in [0, 1] (Hudec 2017/2018)."""
    raise NotImplementedError("UC-022")


def quality_qc(truth: float, cov: float, tnorm: str = "product", c_min: float = 0.5) -> float:
    """Qc = t(truth, C) if C >= c_min else 0."""
    raise NotImplementedError("UC-022")


def regional_quality(
    per_region_truth: dict[str, float], weights: dict[str, float] | None = None
) -> float:
    """Regional quality of one summary across regions (Hudec et al. 2022)."""
    raise NotImplementedError("UC-022")
