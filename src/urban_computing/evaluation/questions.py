"""Seeded evaluation questions drawn from observed UC-014 connections."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from pathlib import Path
from random import Random

import numpy as np
import pandas as pd

from urban_computing.assistant.contract import Question
from urban_computing.assistant.crisp import _WEEKDAY_GROUPS, hub_stop_keys
from urban_computing.assistant.engine import (
    FALLBACK_MIN_CONNECTIONS,
    VOCAB_PATH,
    personal_slack,
)
from urban_computing.data.arrivals import _stop_key
from urban_computing.fuzzy.truth import fuzzy_proportion
from urban_computing.fuzzy.vocabulary import load_vocabulary

_MIN_BORDERLINE = 15
_BORDERLINE_DISTANCE = 0.05
_ROUTE_COLUMNS = {"arr_line": "line", "arr_product": "product"}


def _official_cohorts(
    arrivals: pd.DataFrame, config: dict
) -> tuple[set[tuple[str, str, str, str, str]], dict[str, int]]:
    """Index measured crisp cohorts and count arrival rows retained after each filter."""
    settings = config["connections"]
    hub_keys = {}
    for hub in settings["hubs"]:
        keys = hub_stop_keys(hub, config)
        hub_keys[hub] = {hub} if keys is None else keys
    stop_keys = (
        _stop_key(arrivals["stop_id"]) if settings.get("hub_stop_ids") else arrivals["stop_name"]
    )
    study_keys = {key for keys in hub_keys.values() for key in keys}
    counts = {"input": len(arrivals)}
    keep = stop_keys.isin(study_keys)
    counts["at_hubs"] = int(keep.sum())
    keep &= arrivals["time_band"].isin(config["time_bands"])
    counts["in_time_bands"] = int(keep.sum())
    keep &= ~arrivals["cancelled"].astype(bool)
    counts["uncancelled"] = int(keep.sum())
    keep &= arrivals["delay_min"].notna()
    counts["measured"] = int(keep.sum())
    measured = arrivals.loc[keep, ["time_band", "weekday", "line", "product"]].assign(
        stop_key=stop_keys.loc[keep]
    )
    cohorts = set()
    for hub, keys in hub_keys.items():
        at_hub = measured.loc[measured["stop_key"].isin(keys)]
        for group, weekdays in _WEEKDAY_GROUPS.items():
            at_group = at_hub.loc[at_hub["weekday"].isin(weekdays)]
            for field, column in _ROUTE_COLUMNS.items():
                routes = at_group[["time_band", column]].dropna().drop_duplicates()
                cohorts.update(
                    (hub, band, group, field, route)
                    for band, route in routes.itertuples(index=False, name=None)
                )
    return cohorts, counts


def _question_set(
    connections: pd.DataFrame, config: dict, seed: int, *, arrivals: pd.DataFrame | None = None
) -> tuple[list[Question], dict]:
    """Sample eligible questions and report input filters and pre-margin segments."""
    settings = config["connections"]
    bands = config["time_bands"]
    vocab = load_vocabulary(Path(config.get("paths", {}).get("vocabulary", VOCAB_PATH)))
    missed = vocab.summarizers["connection_slack_minutes"]["missed"]
    # D-026: the crisp decision thresholds are the fuzzy word crossovers (methods §5).
    boundaries = config["crisp_baseline"]["decision_thresholds"].values()
    measured = connections.loc[
        connections["b_cancelled"].fillna(False)
        | (connections["actual_gap_min"].notna() & connections["planned_gap_min"].notna())
    ]
    retained = measured.loc[
        measured["hub"].isin(settings["hubs"]) & measured["time_band"].isin(bands)
    ]
    official, arrival_counts = None, None
    if arrivals is not None:
        official, arrival_counts = _official_cohorts(arrivals, config)
    excluded = {"missing_route": 0, "insufficient_connections": 0, "no_official_cohort": 0}
    eligible = 0
    strata = defaultdict(list)
    for (hub, band), at_time in retained.groupby(["hub", "time_band"], sort=True, observed=True):
        for group, weekdays in _WEEKDAY_GROUPS.items():
            at_group = at_time.loc[at_time["weekday"].isin(weekdays)]
            # Product questions remain eligible when a band has enough observations
            # across lines but too few on any individual line.
            for field in _ROUTE_COLUMNS:
                for route, segment in at_group.groupby(
                    field, sort=True, dropna=False, observed=True
                ):
                    if pd.isna(route) or not route:
                        excluded["missing_route"] += 1
                        continue
                    if len(segment) < FALLBACK_MIN_CONNECTIONS:
                        excluded["insufficient_connections"] += 1
                        continue
                    # Official eligibility is independent of the fuzzy connection rows.
                    if official is not None and (hub, band, group, field, route) not in official:
                        excluded["no_official_cohort"] += 1
                        continue
                    eligible += 1
                    for margin in sorted(set(settings["user_margins_minutes"])):
                        slack = personal_slack(
                            segment, margin, settings["min_transfer_minutes_default"]
                        )
                        p_miss = fuzzy_proportion(np.sort(missed(slack)))
                        borderline = any(
                            abs(p_miss - boundary) <= _BORDERLINE_DISTANCE + 1e-12
                            for boundary in boundaries
                        )
                        strata[hub, band, group, margin].append(
                            (field, route, len(segment), bool(borderline))
                        )

    missing_hubs = set(settings["hubs"]) - {key[0] for key in strata}
    missing_margins = set(settings["user_margins_minutes"]) - {key[3] for key in strata}
    eligible_bands = retained.groupby("time_band", observed=True).size()
    missing_bands = {
        band for band in bands if eligible_bands.get(band, 0) >= FALLBACK_MIN_CONNECTIONS
    } - {key[1] for key in strata}
    if missing_hubs or missing_bands or missing_margins:
        raise ValueError(
            "Insufficient eligible segments for configured coverage: "
            f"hubs={sorted(missing_hubs)}, bands={sorted(missing_bands)}, "
            f"margins={sorted(missing_margins)}"
        )

    rng = Random(seed)
    keys = sorted(strata)
    rng.shuffle(keys)
    queues = {}
    for key in keys:
        rng.shuffle(strata[key])
        queues[key] = deque(strata[key])

    selected = [(key, queues[key].popleft()) for key in keys]
    n_borderline = sum(candidate[3] for _, candidate in selected)
    if n_borderline < _MIN_BORDERLINE:
        for key in keys:
            remaining = deque()
            for candidate in queues[key]:
                if candidate[3] and n_borderline < _MIN_BORDERLINE:
                    selected.append((key, candidate))
                    n_borderline += 1
                else:
                    remaining.append(candidate)
            queues[key] = remaining
            if n_borderline == _MIN_BORDERLINE:
                break
        if n_borderline < _MIN_BORDERLINE:
            raise ValueError(f"Need {_MIN_BORDERLINE} borderline questions, found {n_borderline}")

    target = max(120, config["evaluation"]["n_questions"])
    while len(selected) < target:
        before = len(selected)
        for key in keys:
            if queues[key]:
                selected.append((key, queues[key].popleft()))
            if len(selected) == target:
                break
        if len(selected) == before:
            raise ValueError(f"Need {target} eligible questions, found {before}")

    questions = []
    segments = {}
    counts = Counter()
    for index, (key, (field, route, n, borderline)) in enumerate(selected, start=1):
        hub, band, group, margin = key
        question_id = f"q{index:04d}"
        questions.append(
            Question.model_validate(
                {
                    "hub": hub,
                    "time_band": band,
                    "weekday_group": group,
                    "margin_min": margin,
                    field: route,
                    "question_id": question_id,
                },
                context={"study_config": config},
            )
        )
        segments[question_id] = {"n": n, "borderline": borderline}
        counts[key] += 1
    manifest = {
        "seed": seed,
        "n_questions": len(questions),
        "n_borderline": sum(segment["borderline"] for segment in segments.values()),
        "connection_counts": {
            "input": len(connections),
            "measured": len(measured),
            "retained": len(retained),  # measured rows in configured hubs and bands
        },
        "candidate_segments": {
            # Count each hub, band, weekday group and line or product before adding margins.
            "input": eligible + sum(excluded.values()),
            "eligible": eligible,
            "excluded": excluded,  # first failed eligibility check per segment
        },
        "strata_counts": [
            {"hub": hub, "time_band": band, "weekday_group": group, "margin_min": margin, "n": n}
            for (hub, band, group, margin), n in sorted(counts.items())
        ],
        "segments": segments,
        "versions": {"numpy": np.__version__, "pandas": pd.__version__},
    }
    if arrival_counts is not None:
        manifest["arrival_counts"] = arrival_counts
    return questions, manifest


def make_questions(connections: pd.DataFrame, config: dict, seed: int) -> list[Question]:
    """Return at least 120 seeded Questions from the UC-014 table and study config.

    Uses complete segments of at least 20 observations and transfer margins in minutes.
    Raises ValueError when coverage, the minimum set size or the borderline quota is infeasible.
    """
    questions, _ = _question_set(connections, config, seed)
    return questions


def write_questions(questions: list[Question], path: Path) -> None:
    """Write the supplied Questions in order as UTF-8 JSON Lines at path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes("".join(f"{question.model_dump_json()}\n" for question in questions).encode())
