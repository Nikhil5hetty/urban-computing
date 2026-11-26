"""Crisp and fuzzy claim checkers (UC-042). Definitions: docs/methods.md §6.

Pure functions: no I/O, inputs are never mutated. The crisp checker follows Stat-to-Text
truth conditions (D-012): each row gets exactly one crisp word, a quantifier is a crisp
proportion threshold. The fuzzy checker is the UC-021 truth engine with the UC-020
vocabulary. Both use the same rows and the same crisp restriction.

Missing vs cancelled (D-023): NaN means "unknown" and the row is dropped by both checkers.
A cancelled connection (departing train B cancelled, `b_cancelled`) is a real outcome for
the passenger, so callers encode its slack as -inf: it is then crisply and fuzzily
`missed` (mu_missed = 1, mu_tight = mu_comfortable = 0) and counts in n.

The SRQ3 crisp *checker* (one crisp word per row) differs by design from the SRQ2 crisp
*baseline* (official punctual / not punctual at 3 min, UC-032): see docs/methods.md §6.

`values` holds one array per attribute (`arrival_delay_minutes`,
`connection_slack_minutes`) and the row attributes used by restrictions: `time_band`
(str), `weekday` (int, 0 = Monday) or `weekday_group` (str), ... A column named
`"<attribute>.<family>"` takes precedence over `"<family>"`, for segments whose arrivals
and connections have different rows.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict

from urban_computing.fuzzy.truth import fuzzy_proportion
from urban_computing.fuzzy.vocabulary import Trapezoid, Vocabulary
from urban_computing.llm.parser import Claim

Disagreement = Literal["none", "crisp_true_fuzzy_false", "crisp_false_fuzzy_true", "n/a"]

FUZZY_TRUE_THRESHOLD = 0.5  # fuzzy_true = truth >= 0.5 (ticket UC-042, H3a)
CRISP_DEFAULTS: dict[str, float] = {
    "punctual_threshold_minutes": 3.0,  # SBB (D-007); config crisp_baseline overrides
    "most_threshold": 0.5,  # Stat-to-Text "more than half" (D-012); config overrides
    "few_threshold": 0.25,  # our choice: Stat-to-Text has no "few"
    "about_half_tolerance": 0.1,  # our choice: |p - 0.5| <= 0.1
}
# Crisp boundaries fixed by a definition instead of the fuzzy crossover (methods §6).
_DEFINED_UPPER: dict[tuple[str, str], str | float] = {
    ("arrival_delay_minutes", "on_time"): "punctual_threshold_minutes",
    ("connection_slack_minutes", "missed"): 0.0,  # slack < 0: transfer impossible
}
_WEEKDAY_GROUPS: dict[str, tuple[int, ...]] = {
    "weekday": (0, 1, 2, 3, 4),
    "monday": (0,),
    "friday": (4,),
    "weekend": (5, 6),
    "all": (0, 1, 2, 3, 4, 5, 6),
}


class CheckResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    claim: Claim
    crisp: bool | None
    fuzzy: float | None
    fuzzy_true: bool | None  # fuzzy >= 0.5
    disagreement: Disagreement
    n: int | None = None  # complete rows in the (restricted) segment
    p_crisp: float | None = None  # crisp proportion behind `crisp`
    p_fuzzy: float | None = None  # fuzzy proportion behind `fuzzy`
    reason: str | None = None  # why the claim could not be checked (n/a)


def _crisp_param(config: Mapping[str, Any], key: str) -> float:
    return float((config.get("crisp_baseline") or {}).get(key, CRISP_DEFAULTS[key]))


def crisp_intervals(
    vocab: Vocabulary, config: Mapping[str, Any]
) -> dict[str, dict[str, tuple[float, float]]]:
    """Crisp interval [lo, hi) per summarizer word, in the attribute's units (minutes).

    Words of one attribute are ordered along the axis; the boundary between neighbours is
    the crossover of the upper word's falling ramp, (c + d) / 2 (membership 0.5 in a
    Ruspini partition), except the boundaries fixed by definition: on_time | slightly_late
    at the punctuality threshold (D-007) and missed | tight at slack 0.
    """
    out: dict[str, dict[str, tuple[float, float]]] = {}
    for attr, words in vocab.summarizers.items():
        order = sorted(words.items(), key=lambda kv: _left(kv[1]))
        bounds: list[float] = []
        for word, t in order[:-1]:
            fixed = _DEFINED_UPPER.get((attr, word))
            if isinstance(fixed, str):
                bounds.append(_crisp_param(config, fixed))
            elif fixed is not None:
                bounds.append(float(fixed))
            else:
                if t.c is None or t.d is None:
                    raise ValueError(f"{attr}.{word}: open right shoulder before the last word")
                bounds.append((float(t.c) + float(t.d)) / 2.0)
        edges = [-np.inf, *bounds, np.inf]
        out[attr] = {w: (edges[i], edges[i + 1]) for i, (w, _) in enumerate(order)}
    return out


def _left(t: Trapezoid) -> float:
    return -np.inf if t.b is None else float(t.b)


def crisp_quantifier(quantifier: str, p: float, config: Mapping[str, Any]) -> bool | None:
    """Crisp truth of quantifier for crisp proportion p in [0, 1]; None if undefined.

    most: p > most_threshold; few: p < few_threshold; about_half: |p - 0.5| <= tol
    (a 1e-12 slack absorbs float error at the boundary). Extended words: None.
    """
    if quantifier == "most":
        return bool(p > _crisp_param(config, "most_threshold"))
    if quantifier == "few":
        return bool(p < _crisp_param(config, "few_threshold"))
    if quantifier == "about_half":
        return bool(abs(p - 0.5) <= _crisp_param(config, "about_half_tolerance") + 1e-12)
    return None


def _column(values: Mapping[str, np.ndarray], attr: str, name: str) -> np.ndarray | None:
    col = values.get(f"{attr}.{name}")
    return (
        np.asarray(col)
        if col is not None
        else (np.asarray(values[name]) if name in values else None)
    )


def _restriction_mask(
    restriction: str | None, values: Mapping[str, np.ndarray], attr: str, n: int
) -> tuple[np.ndarray | None, str | None]:
    """Crisp 0/1 restriction over the attribute's rows, or (None, reason)."""
    mask = np.ones(n, dtype=bool)
    if not restriction:
        return mask, None
    for part in restriction.split("&"):
        family, _, key = part.partition("=")
        if family == "weekday_group" and _column(values, attr, "weekday") is not None:
            if key not in _WEEKDAY_GROUPS:
                return None, f"restriction: unknown weekday_group {key!r}"
            col = _column(values, attr, "weekday")
            sel = np.isin(col, _WEEKDAY_GROUPS[key])
        else:
            col = _column(values, attr, family)
            if col is None:
                return None, f"restriction: no `{family}` column in values"
            sel = col == key
        if col.shape[0] != n:
            raise ValueError(f"`{family}` has {col.shape[0]} rows, `{attr}` has {n}")
        mask &= np.asarray(sel, dtype=bool)
    return mask, None


def _na(claim: Claim, reason: str, fuzzy: float | None = None, **kw: Any) -> CheckResult:
    return CheckResult(claim=claim, crisp=None, fuzzy=fuzzy,
                       fuzzy_true=None if fuzzy is None else bool(fuzzy >= FUZZY_TRUE_THRESHOLD),
                       disagreement="n/a", reason=reason, **kw)  # fmt: skip


def check(
    claim: Claim, values: dict[str, np.ndarray], vocab: Vocabulary, config: dict
) -> CheckResult:
    """Score one claim against the segment's raw values with both checkers.

    Inputs: a parsed claim (UC-041 canonical words), the segment's value arrays (see
    module docstring), the vocabulary, the study config (`crisp_baseline`). Returns crisp
    truth (bool), fuzzy truth in [0, 1], fuzzy_true (>= 0.5) and the disagreement class;
    everything None / "n/a" with a `reason` when the claim cannot be checked (status not
    ok, unknown word, missing column, empty segment). Raises ValueError if a restriction
    column and the attribute differ in length.
    """
    if claim.status != "ok":
        return _na(claim, f"status {claim.status}")
    q, s = claim.quantifier, claim.summarizer
    quant = next((ws[q] for ws in vocab.quantifiers.values() if q in ws), None)
    if quant is None:
        return _na(claim, f"quantifier {q!r} not in vocabulary")
    attr, _, word = (s or "").partition(":")
    if word not in vocab.summarizers.get(attr, {}):
        return _na(claim, f"summarizer {s!r} not in vocabulary")
    if attr not in values:
        return _na(claim, f"values: no `{attr}` array in segment")

    x = np.asarray(values[attr], dtype=np.float64).ravel()
    mask, why = _restriction_mask(claim.restriction, values, attr, x.size)
    if mask is None:
        return _na(claim, why or "restriction")
    rows = x[mask & ~np.isnan(x)]
    if rows.size == 0:
        return _na(claim, "empty segment after restriction / missing values", n=0)

    lo, hi = crisp_intervals(vocab, config)[attr][word]
    p_crisp = float(np.mean((rows >= lo) & (rows < hi)))
    p_fuzzy = fuzzy_proportion(vocab.summarizers[attr][word](rows))
    fuzzy = float(np.asarray(quant(np.asarray(p_fuzzy))))
    fuzzy_true = bool(fuzzy >= FUZZY_TRUE_THRESHOLD)
    crisp = crisp_quantifier(str(q), p_crisp, config)
    extra = {"n": int(rows.size), "p_crisp": p_crisp, "p_fuzzy": p_fuzzy}
    if crisp is None:
        return _na(claim, f"no crisp definition for {q!r}", fuzzy=fuzzy, **extra)
    if crisp == fuzzy_true:
        dis: Disagreement = "none"
    else:
        dis = "crisp_true_fuzzy_false" if crisp else "crisp_false_fuzzy_true"
    return CheckResult(claim=claim, crisp=crisp, fuzzy=fuzzy, fuzzy_true=fuzzy_true,
                       disagreement=dis, **extra)  # fmt: skip
