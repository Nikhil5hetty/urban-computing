"""Summary miner (UC-023): enumerate Q x S (x R) summaries over one segment.

Pure NumPy, no I/O. For each summarizer word S of each attribute in `values` and each
quantifier Q of the chosen set:
- the simple summary "Q x are S" (truth §2, coverage 1, Qc = v; methods §3.2), and
- one restricted summary "Q R x are S" per restriction R (truth §2, coverage §3.1, Qc §3.2).
Missing values (NaN) are dropped row-wise (methods §2); `n` counts complete rows and
`n_dropped` the NaN rows (e.g. cancelled arrivals). Conventions: docs/methods.md §4.

`mine` takes arbitrary restriction masks (frozen interface). `mine_categorical` is the
fast path for a partition family (each row has at most one value, e.g. `line`): it gives
the same records as `mine` with crisp masks `family == value`, in O(rows) per family.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from urban_computing.fuzzy.quality import (
    DEFAULT_COVERAGE,
    coverage,
    coverage_from_ratio,
    quality_qc,
)
from urban_computing.fuzzy.truth import truth_restricted, truth_simple
from urban_computing.fuzzy.vocabulary import Trapezoid, Vocabulary

SMALL_N = 30  # records with fewer complete rows are kept but flagged small_n (ticket UC-023)
QC_DEFAULTS: dict[str, Any] = {**DEFAULT_COVERAGE, "coverage_threshold": 0.5, "qc_tnorm": "product"}


@dataclass(frozen=True)
class SummaryRecord:
    protoform: str  # "simple" | "restricted"
    quantifier: str  # e.g. "most"
    summarizer: str  # e.g. "arrival_delay_minutes:on_time"
    restriction: str | None  # e.g. "time_band=morning_peak&product=IC"; None = whole segment
    segment: str  # e.g. "hub=Olten" or "network"
    n: int  # rows in the segment (crisp count)
    truth: float
    coverage: float | None
    quality: float | None
    half: str | None  # "first" | "second" | None (both)
    sentence: str  # deterministic English rendering
    small_n: bool = False
    n_dropped: int = 0  # rows dropped as missing (NaN) in the segment / R (UC-023, #39)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------- rendering

QUANTIFIER_TEXT = {
    "few": "Few",
    "about_half": "About half",
    "most": "Most",
    "almost_none": "Almost none",
    "almost_all": "Almost all",
}
ATTRIBUTE_NOUN = {"arrival_delay_minutes": "arrivals", "connection_slack_minutes": "connections"}
_MODIFIER_FAMILIES = ("operator", "product", "line")  # rendered before the noun
TIME_BAND_TEXT = {
    "early": "in the early morning",
    "morning_peak": "in the morning peak",
    "midday": "at midday",
    "evening_peak": "in the evening peak",
    "evening": "in the evening",
    "night": "at night",
}
WEEKDAY_TEXT = {
    "weekday": "on weekdays",
    "monday": "on Mondays",
    "friday": "on Fridays",
    "weekend": "at weekends",
    "all": "",
}


def _parts(label: str | None) -> list[tuple[str, str]]:
    if not label:
        return []
    return [(f, v) for f, _, v in (p.partition("=") for p in label.split("&")) if v]


def render_sentence(
    quantifier: str, summarizer: str, restriction: str | None = None, segment: str = "network"
) -> str:
    """Template-based English sentence, e.g. "About half of the IC arrivals in the morning
    peak are slightly late." Deterministic; uses only the given words and labels."""
    attr, _, word = summarizer.partition(":")
    q = QUANTIFIER_TEXT.get(quantifier, quantifier.replace("_", " ").capitalize())
    noun = ATTRIBUTE_NOUN.get(attr, "records")
    mods: list[str] = []
    tail: list[str] = []
    for family, value in _parts(segment if segment != "network" else None):
        tail.append(f"at {value}" if family == "hub" else f"with {family} {value}")
    for family, value in _parts(restriction):
        if family in _MODIFIER_FAMILIES:
            mods.append(value)
        elif family == "time_band":
            tail.append(TIME_BAND_TEXT.get(value, f"in the {value.replace('_', ' ')}"))
        elif family == "weekday_group":
            tail.append(WEEKDAY_TEXT.get(value, f"on {value}"))
        elif family == "canton":
            tail.append(f"in canton {value}")
        else:
            tail.append(f"with {family.replace('_', ' ')} {value}")
    subject = " ".join([*mods, noun])
    rest = " ".join(t for t in tail if t)
    return f"{q} of the {subject}{' ' + rest if rest else ''} are {word.replace('_', ' ')}."


# ---------------------------------------------------------------------------- helpers


def _qc_params(mining: Mapping[str, Any] | None) -> dict[str, Any]:
    p = dict(QC_DEFAULTS)
    p.update({k: v for k, v in (mining or {}).items() if k in QC_DEFAULTS})
    return p


def _quality(truth: float, cov: float | None, p: Mapping[str, Any]) -> float | None:
    if cov is None or math.isnan(truth) or math.isnan(cov):
        return None
    return quality_qc(truth, cov, tnorm=p["qc_tnorm"], c_min=float(p["coverage_threshold"]))


def _record(
    protoform: str, q: str, s: str, r: str | None, segment: str, n: int, n_dropped: int,
    truth: float, cov: float | None, p: Mapping[str, Any], half: str | None, min_n: int,
) -> SummaryRecord:  # fmt: skip
    if math.isnan(truth):
        cov = None
    return SummaryRecord(
        protoform=protoform,
        quantifier=q,
        summarizer=s,
        restriction=r,
        segment=segment,
        n=int(n),
        truth=float(truth),
        coverage=None if cov is None else float(cov),
        quality=_quality(truth, cov, p),
        half=half,
        sentence=render_sentence(q, s, r, segment),
        small_n=bool(n < min_n),
        n_dropped=int(n_dropped),
    )


def _words(values: Mapping[str, np.ndarray], vocab: Vocabulary) -> list[tuple[str, str, Trapezoid]]:
    return [
        (attr, word, fn)
        for attr in sorted(values)
        for word, fn in vocab.summarizers.get(attr, {}).items()
    ]


def _quantifiers(vocab: Vocabulary, quantifier_set: str) -> dict[str, Trapezoid]:
    if quantifier_set not in vocab.quantifiers:
        raise ValueError(f"unknown quantifier set {quantifier_set!r}")
    return vocab.quantifiers[quantifier_set]


# ---------------------------------------------------------------------------- generic


def mine(
    values: dict[str, np.ndarray],
    restrictions: dict[str, np.ndarray],
    vocab: Vocabulary,
    beta: float = 0.6,
    segment: str = "network",
    half: str | None = None,
    quantifier_set: str = "core",
    tnorm: str = "product",
    mining: Mapping[str, Any] | None = None,
    min_n: int = SMALL_N,
    include_simple: bool = True,
) -> list[SummaryRecord]:
    """Enumerate Q x S (x R) summaries over one segment.

    values: attribute name -> raw values (e.g. {"arrival_delay_minutes": delays})
    restrictions: restriction label -> membership array (crisp masks as 0/1 floats)
    Returns ALL records (valid and invalid); callers filter on truth >= beta (`beta` is not
    used for filtering here). All arrays must have the same length. `tnorm` is the truth
    t-norm (§2); Qc always uses `mining.qc_tnorm` (product, D-027) with
    `mining.coverage_r1/r2` and `mining.coverage_threshold` (defaults: D-027 values).
    `n` = complete rows (in R: rows with mu_R > 0), `n_dropped` = NaN rows there; records
    with n < `min_n` are flagged small_n. Order: attribute (sorted), word, then the simple
    summary and the restrictions in the given order, each over the quantifiers.
    """
    p = _qc_params(mining)
    quants = _quantifiers(vocab, quantifier_set)
    lengths = {k: np.asarray(v).size for k, v in values.items()}
    lengths.update({f"restriction {k}": np.asarray(v).size for k, v in restrictions.items()})
    if len(set(lengths.values())) > 1:
        raise ValueError(f"values and restrictions must have the same length: {lengths}")
    out: list[SummaryRecord] = []
    for attr, word, fn in _words(values, vocab):
        x = np.asarray(values[attr], dtype=np.float64)
        missing = np.isnan(x)
        mu_s = fn(x)
        s = f"{attr}:{word}"
        if include_simple:
            n, n_drop = int((~missing).sum()), int(missing.sum())
            cov = coverage(None, mu_s, p)
            for q, qfn in quants.items():
                v = truth_simple(mu_s, qfn)
                out.append(
                    _record("simple", q, s, None, segment, n, n_drop, v, cov, p, half, min_n)
                )
        for label, mask in restrictions.items():
            mu_r = np.asarray(mask, dtype=np.float64)
            in_r = mu_r > 0
            n, n_drop = int((in_r & ~missing).sum()), int((in_r & missing).sum())
            cov = coverage(mu_r, mu_s, p)
            for q, qfn in quants.items():
                v = truth_restricted(mu_r, mu_s, qfn, tnorm)  # type: ignore[arg-type]
                out.append(
                    _record("restricted", q, s, label, segment, n, n_drop, v, cov, p, half, min_n)
                )
    return out


# ---------------------------------------------------------------------------- fast path


def mine_categorical(
    values: dict[str, np.ndarray],
    family: str,
    codes: Sequence[Any] | np.ndarray,
    vocab: Vocabulary,
    segment: str = "network",
    half: str | None = None,
    quantifier_set: str = "core",
    mining: Mapping[str, Any] | None = None,
    min_n: int = SMALL_N,
    labels: Sequence[str] | None = None,
) -> list[SummaryRecord]:
    """Restricted summaries for every value of one partition family, in O(rows).

    `codes[i]` is row i's value of `family` (None / NaN = no value: in no R, but still a
    record for coverage). Equivalent to `mine(values, {f"{family}={v}": codes == v}, ...,
    include_simple=False)` with crisp masks, for which product and min t-norms coincide.
    `labels` selects and orders the values (default: sorted distinct values).
    """
    p = _qc_params(mining)
    quants = _quantifiers(vocab, quantifier_set)
    arr = np.asarray(codes, dtype=object)
    present = np.array([c is not None and c == c for c in arr], dtype=bool)  # c == c: not NaN
    keys = [str(c) for c in arr]
    uniq = sorted({k for k, ok in zip(keys, present, strict=True) if ok})
    chosen = [str(v) for v in labels] if labels is not None else uniq
    index = {v: i for i, v in enumerate(uniq)}
    idx = np.array([index[k] if ok else -1 for k, ok in zip(keys, present, strict=True)], dtype=int)
    k = len(uniq)
    r1, r2 = float(p["coverage_r1"]), float(p["coverage_r2"])
    out: list[SummaryRecord] = []
    for attr, word, fn in _words(values, vocab):
        x = np.asarray(values[attr], dtype=np.float64)
        if x.size != arr.size:
            raise ValueError(f"`{attr}` has {x.size} rows, codes have {arr.size}")
        missing = np.isnan(x)
        mu_s = fn(x)
        n_all = int((~missing).sum())
        sel = present & ~missing
        counts = np.bincount(idx[sel], minlength=k)
        sums = np.bincount(idx[sel], weights=mu_s[sel], minlength=k)
        support = np.bincount(idx[sel], weights=(mu_s[sel] > 0).astype(float), minlength=k)
        dropped = np.bincount(idx[present & missing], minlength=k)
        s = f"{attr}:{word}"
        for v in chosen:
            j = index.get(v)
            n = int(counts[j]) if j is not None else 0
            n_drop = int(dropped[j]) if j is not None else 0
            prop = float(sums[j] / n) if n else float("nan")
            i_c = float(support[j] / n_all) if (j is not None and n_all) else float("nan")
            cov = coverage_from_ratio(i_c, r1, r2)
            for q, qfn in quants.items():
                truth = (
                    float("nan") if math.isnan(prop) else float(np.asarray(qfn(np.asarray(prop))))
                )
                out.append(
                    _record("restricted", q, s, f"{family}={v}", segment, n, n_drop, truth,
                            cov, p, half, min_n)
                )  # fmt: skip
    return out


# ---------------------------------------------------------------------------- reports


def qc_drop_report(records: Sequence[SummaryRecord], beta: float = 0.6) -> dict[str, dict]:
    """Per quantifier: valid summaries (truth >= beta) and how many of them Qc drops
    (quality == 0, i.e. coverage < c_min). Restricted `few` summaries can get low coverage
    by design (few records in R and S): PM review of #54."""
    out: dict[str, dict] = {}
    for r in records:
        if math.isnan(r.truth) or r.truth < beta:
            continue
        d = out.setdefault(r.quantifier, {"valid": 0, "dropped_by_qc": 0})
        d["valid"] += 1
        if r.quality is not None and r.quality == 0.0:
            d["dropped_by_qc"] += 1
    return dict(sorted(out.items()))
