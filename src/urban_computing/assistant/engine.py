"""Perception-aware connection-risk decision with faithful explanation (UC-031).

CWW pipeline (docs/methods.md §5, decision D-029):
1. Segment: the question's connections at the hub (UC-014 already matched hub stops by id),
   arriving line (else product), departing line/product if given, time band and weekday
   group. Fewer than `FALLBACK_MIN_CONNECTIONS` rows -> fallback to the arriving line's
   arrivals at the hub (selected by stop id like the crisp baseline, UC-032).
2. Encoder: personal slack s = margin + (actual gap - planned gap) - min transfer time;
   a cancelled departure (`b_cancelled`) is s = -inf (missed; D-023 convention), an
   unknown gap (NaN, e.g. DST window D-025) is dropped. mu = mu_missed(s).
   Fallback: mu = late_for_my_transfer(arrival delay; margin) (D-010).
3. Engine: p_miss = fuzzy proportion of mu (truth engine, §2).
4. Decoder: decision = argmax over the fuzzy decision words on p_miss
   (config/vocabulary.yaml `decision_sets`), ties -> the more cautious word.
5. Explanation: the best core-quantifier sentence on p_miss, plus up to three valid summaries
   (truth >= beta) with the highest Qc, mined with the hub's arrivals as the segment.
`verify_answer` recomputes every number from the data (invariant I4).
"""

from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from urban_computing.assistant.contract import Answer, Decision, Explanation, Provenance, Question
from urban_computing.assistant.crisp import (
    _WEEKDAY_GROUPS,
    NoArrivalsError,
    crisp_answer,
    hub_stop_keys,
)
from urban_computing.data.arrivals import _stop_key
from urban_computing.fuzzy.miner import QUANTIFIER_TEXT, mine
from urban_computing.fuzzy.truth import fuzzy_proportion, truth_restricted, truth_simple
from urban_computing.fuzzy.vocabulary import Trapezoid, Vocabulary

FALLBACK_MIN_CONNECTIONS = 20  # fewer matching connections -> arrivals fallback (D-029)
MAX_SUMMARIES = 3
CAUTION = ("safe", "at_risk", "risky")  # tie-break order: later = more cautious
TIE_TOL = 1e-12  # memberships this close count as a tie (float error at the crossovers)
OWN_CONNECTIONS = "own_connections"  # Explanation.restriction marker of the p_miss sentence
OWN_ARRIVALS = "own_arrivals"  # ... in the arrivals fallback
VOCAB_PATH = Path(__file__).resolve().parents[3] / "config" / "vocabulary.yaml"
_FAMILY_COLUMN = {"operator": "operator_abbr"}


class NoDataError(ValueError):
    """Neither connections nor arrivals match the question's segment."""


# ---------------------------------------------------------------------------- decision


@lru_cache(maxsize=4)
def _decision_sets_from_file(path: str) -> dict[str, Trapezoid]:
    import yaml

    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")).get("decision_sets") or {}
    return {w: Trapezoid(*v) for w, v in raw.items()}


def decision_sets(config: dict) -> dict[str, Trapezoid]:
    """Fuzzy decision words over p_miss: config["decision_sets"] if given, else the
    `decision_sets` section of config/vocabulary.yaml (or `paths.vocabulary`)."""
    if config.get("decision_sets"):
        return {w: Trapezoid(*v) for w, v in config["decision_sets"].items()}
    path = (config.get("paths") or {}).get("vocabulary") or VOCAB_PATH
    sets = _decision_sets_from_file(str(path))
    if set(sets) != set(CAUTION):
        raise ValueError(f"decision_sets must define {CAUTION}, got {sorted(sets)}")
    return sets


def decide(p_miss: float, sets: dict[str, Trapezoid]) -> Decision:
    """argmax_w mu_w(p_miss); ties (within TIE_TOL) go to the more cautious word
    (risky > at_risk > safe), so p_miss = 0.075 / 0.25 give at_risk / risky like the crisp
    baseline's thresholds (D-026)."""
    mus = {w: float(np.asarray(sets[w](np.asarray(p_miss)))) for w in CAUTION}
    best = max(mus.values())
    return [w for w in CAUTION if mus[w] >= best - TIE_TOL][-1]  # type: ignore[return-value]


# ---------------------------------------------------------------------------- segments


def _in_group(weekday: pd.Series, group: str) -> pd.Series:
    return weekday.isin(_WEEKDAY_GROUPS[group])


def connection_segment(question: Question, connections: pd.DataFrame) -> pd.DataFrame:
    """Rows of CONNECTIONS for the question (hub, lines/products, time band, weekday group)."""
    c = connections
    sel = (c["hub"] == question.hub) & (c["time_band"] == question.time_band)
    sel &= _in_group(c["weekday"], question.weekday_group)
    sel &= (
        (c["arr_line"] == question.arr_line)
        if question.arr_line
        else (c["arr_product"] == question.arr_product)
    )
    if question.dep_line:
        sel &= c["dep_line"] == question.dep_line
    elif question.dep_product:
        sel &= c["dep_product"] == question.dep_product
    return c.loc[sel]


def personal_slack(seg: pd.DataFrame, margin_min: float, min_transfer_min: float) -> np.ndarray:
    """s = margin + (actual gap - planned gap) - min transfer (minutes); -inf if B cancelled.

    The observed connection tells how delays shift a transfer (actual - planned gap =
    departure delay - arrival delay); the passenger plans `margin_min` minutes (D-029).
    """
    shift = seg["actual_gap_min"].astype("float64") - seg["planned_gap_min"].astype("float64")
    s = np.array((margin_min + shift - min_transfer_min).to_numpy(), dtype=np.float64)  # copy
    s[seg["b_cancelled"].fillna(False).astype(bool).to_numpy()] = -np.inf
    return s


def hub_arrivals(question: Question, arrivals: pd.DataFrame, config: dict) -> pd.DataFrame:
    """All arrivals at the hub's stops (by stop id; exact name only without an id mapping)."""
    keys = hub_stop_keys(question.hub, config)
    if keys is None:
        return arrivals.loc[arrivals["stop_name"] == question.hub]
    return arrivals.loc[_stop_key(arrivals["stop_id"]).isin(keys).fillna(False).astype(bool)]


def own_arrivals(hub_rows: pd.DataFrame, question: Question) -> pd.DataFrame:
    """The arriving line's (else product's) arrivals in the question's time band / weekdays."""
    a = hub_rows
    sel = (a["time_band"] == question.time_band) & _in_group(a["weekday"], question.weekday_group)
    sel &= (
        (a["line"] == question.arr_line)
        if question.arr_line
        else (a["product"] == question.arr_product)
    )
    return a.loc[sel & ~a["cancelled"].astype(bool)]


def _mask(rows: pd.DataFrame, label: str | None) -> np.ndarray:
    """Crisp 0/1 restriction mask over `rows` for a label like 'line=IC1&time_band=midday'."""
    mask = np.ones(len(rows), dtype=bool)
    for part in (label or "").split("&"):
        if not part:
            continue
        family, _, value = part.partition("=")
        if family == "weekday_group":
            mask &= _in_group(rows["weekday"], value).to_numpy()
        else:
            mask &= (rows[_FAMILY_COLUMN.get(family, family)] == value).to_numpy()
    return mask.astype(np.float64)


def _labels(question: Question) -> list[str]:
    parts = [
        f"line={question.arr_line}" if question.arr_line else f"product={question.arr_product}",
        f"time_band={question.time_band}",
    ]
    if question.weekday_group != "all":
        parts.append(f"weekday_group={question.weekday_group}")
    return [*parts, "&".join(sorted(parts))]


# ---------------------------------------------------------------------------- encoder


def _p_miss(
    question: Question,
    connections: pd.DataFrame,
    arrivals: pd.DataFrame,
    vocab: Vocabulary,
    config: dict,
) -> tuple[float, int, bool, str]:
    """(p_miss, n complete rows, fallback, summarizer) for the question."""
    seg = connection_segment(question, connections)
    if len(seg) >= FALLBACK_MIN_CONNECTIONS:
        min_transfer = float(config["connections"]["min_transfer_minutes_default"])
        s = personal_slack(seg, question.margin_min, min_transfer)
        mu = vocab.summarizers["connection_slack_minutes"]["missed"](s)
        n = int((~np.isnan(s)).sum())
        if n == 0:
            raise NoDataError("no matching connection has a known gap")
        return fuzzy_proportion(mu), n, False, "connection_slack_minutes:missed"
    own = own_arrivals(hub_arrivals(question, arrivals, config), question)
    delay = own["delay_min"].astype("float64").to_numpy()
    n = int((~np.isnan(delay)).sum())
    if n == 0:
        raise NoDataError(
            f"fewer than {FALLBACK_MIN_CONNECTIONS} connections and no measured arrivals for "
            f"{question.arr_line or question.arr_product} at {question.hub}"
        )
    mu = vocab.late_for_my_transfer(question.margin_min)(delay)
    return fuzzy_proportion(mu), n, True, "arrival_delay_minutes:late_for_my_transfer"


def _best_quantifier(p: float, vocab: Vocabulary) -> tuple[str, float]:
    """Core quantifier with the highest truth mu_Q(p) (ties: vocabulary order)."""
    core = vocab.quantifiers["core"]
    scores = [(q, float(np.asarray(fn(np.asarray(p))))) for q, fn in core.items()]
    return max(scores, key=lambda t: t[1])


def _own_sentence(question: Question, q: str, fallback: bool) -> str:
    qt = QUANTIFIER_TEXT[q]
    m = f"{question.margin_min:g}"
    if fallback:
        what = question.arr_line or question.arr_product
        return (
            f"With {m} minutes to change, {qt.lower()} of the {what} arrivals at "
            f"{question.hub} are too late for your transfer."
        )
    where = f"of your connections at {question.hub}"
    return f"With {m} minutes to change, {qt.lower()} {where} are missed."


def _config_hash(config: dict) -> str:
    blob = json.dumps(config, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------- public


def answer(
    question: Question,
    connections: pd.DataFrame,
    arrivals: pd.DataFrame,
    vocab: Vocabulary,
    config: dict,
) -> Answer:
    """Decision word + explanation from the same truth computation (invariant I4).

    Inputs: the Question, CONNECTIONS and ARRIVALS frames (schemas.py), the vocabulary and
    the study config (`connections.min_transfer_minutes_default`, `mining`, optional
    `connections.hub_stop_ids`, `decision_sets`). Returns an Answer with the fuzzy
    decision, p_miss, explanations (every truth >= beta) and the crisp official view
    (UC-032) when arrivals exist. Raises NoDataError if nothing matches the question.
    """
    beta = float(config["mining"]["beta"])
    p_miss, n, fallback, summarizer = _p_miss(question, connections, arrivals, vocab, config)
    decision = decide(p_miss, decision_sets(config))

    explanations: list[Explanation] = []
    q, truth = _best_quantifier(p_miss, vocab)
    if truth >= beta:
        explanations.append(
            Explanation(
                sentence=_own_sentence(question, q, fallback),
                quantifier=q,
                summarizer=summarizer,
                restriction=OWN_ARRIVALS if fallback else OWN_CONNECTIONS,
                truth=truth,
                coverage=1.0,
                quality=truth,
                n=n,
            )
        )

    hub_rows = hub_arrivals(question, arrivals, config)
    if len(hub_rows):
        masks = {label: _mask(hub_rows, label) for label in _labels(question)}
        recs = mine(
            {"arrival_delay_minutes": hub_rows["delay_min"].astype("float64").to_numpy()},
            masks,
            vocab,
            beta,
            segment=f"hub={question.hub}",
            mining=config["mining"],
            tnorm=str(config["mining"].get("tnorm", "product")),
        )
        valid = [
            r
            for r in recs
            if not math.isnan(r.truth)
            and r.truth >= beta
            and r.quality is not None
            and r.quality > 0
            and not r.small_n
        ]
        valid.sort(key=lambda r: (-(r.quality or 0.0), -r.truth, r.sentence))
        for r in valid[:MAX_SUMMARIES]:
            explanations.append(
                Explanation(
                    sentence=r.sentence,
                    quantifier=r.quantifier,
                    summarizer=r.summarizer,
                    restriction=r.restriction,
                    truth=r.truth,
                    coverage=r.coverage,
                    quality=r.quality,
                    n=r.n,
                )
            )

    crisp_decision, crisp_sentences = None, []
    try:
        crisp = crisp_answer(question, arrivals, config)
        crisp_decision, crisp_sentences = crisp.crisp_decision, crisp.crisp_sentences
    except NoArrivalsError:
        pass
    period = config["data"]["period"]
    return Answer(
        question=question,
        decision=decision,
        p_miss=p_miss,
        explanations=explanations,
        crisp_decision=crisp_decision,
        crisp_sentences=crisp_sentences,
        provenance=Provenance(
            period=f"{period['start']}..{period['end']}",
            config_hash=_config_hash(config),
            fallback=fallback,
        ),
    )


def verify_answer(
    ans: Answer,
    connections: pd.DataFrame,
    arrivals: pd.DataFrame,
    vocab: Vocabulary,
    config: dict,
    tol: float = 1e-9,
) -> bool:
    """Recompute every explanation's truth from the data; True iff all match (I4).

    Also recomputes p_miss and the decision word from it, and checks that no explanation
    states a truth below beta.
    """
    question, beta = ans.question, float(config["mining"]["beta"])
    p_miss, _, fallback, _ = _p_miss(question, connections, arrivals, vocab, config)
    if ans.p_miss is None or abs(p_miss - ans.p_miss) > tol or fallback != ans.provenance.fallback:
        return False
    if decide(p_miss, decision_sets(config)) != ans.decision:
        return False
    hub_rows = hub_arrivals(question, arrivals, config)
    delays = hub_rows["delay_min"].astype("float64").to_numpy()
    tnorm = str(config["mining"].get("tnorm", "product"))
    for e in ans.explanations:
        if e.truth < beta:
            return False
        qfn = vocab.quantifiers["core"][e.quantifier]
        if e.restriction in (OWN_CONNECTIONS, OWN_ARRIVALS):
            truth = float(np.asarray(qfn(np.asarray(p_miss))))
        else:
            attr, _, word = e.summarizer.partition(":")
            mu_s = vocab.summarizers[attr][word](delays)
            truth = (
                truth_simple(mu_s, qfn)
                if e.restriction is None
                else truth_restricted(_mask(hub_rows, e.restriction), mu_s, qfn, tnorm)
            )
        if math.isnan(truth) or abs(truth - e.truth) > tol:
            return False
    return True
