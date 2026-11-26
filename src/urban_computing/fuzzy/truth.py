"""Truth (validity) of linguistic summaries (UC-021). INTERFACE stub.

Works on membership arrays so it does not depend on the vocabulary implementation.
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from urban_computing.fuzzy.vocabulary import MembershipFn

TNorm = Literal["product", "min"]


def fuzzy_proportion(
    mu_S: np.ndarray, mu_R: np.ndarray | None = None, tnorm: TNorm = "product"
) -> float:
    """sum t(mu_R, mu_S) / sum mu_R (or mean(mu_S) if mu_R is None). nan if sum mu_R == 0."""
    raise NotImplementedError("UC-021")


def truth_simple(mu_S: np.ndarray, Q: MembershipFn) -> float:
    """v("Q x are S") = mu_Q(mean(mu_S))."""
    raise NotImplementedError("UC-021")


def truth_restricted(
    mu_R: np.ndarray, mu_S: np.ndarray, Q: MembershipFn, tnorm: TNorm = "product"
) -> float:
    """v("Q R x are S") = mu_Q(sum t(mu_R, mu_S) / sum mu_R); nan if sum mu_R == 0."""
    raise NotImplementedError("UC-021")
