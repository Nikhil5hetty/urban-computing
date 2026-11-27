"""Seeded evaluation questions drawn from observed UC-014 connections."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from pathlib import Path
from random import Random

import numpy as np
import pandas as pd

from urban_computing.assistant.contract import Question
from urban_computing.assistant.crisp import _WEEKDAY_GROUPS, _segment
from urban_computing.assistant.engine import (
    FALLBACK_MIN_CONNECTIONS,
    VOCAB_PATH,
    personal_slack,
)
from urban_computing.fuzzy.truth import fuzzy_proportion
from urban_computing.fuzzy.vocabulary import load_vocabulary

_MIN_BORDERLINE = 15
_BORDERLINE_DISTANCE = 0.05


def _question_set(
    connections: pd.DataFrame, config: dict, seed: int, *, arrivals: pd.DataFrame | None = None
) -> tuple[list[Question], dict]:
    """Sample eligible questions and collect the manifest for the same selection."""
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
    strata = defaultdict(list)
    for (hub, band), at_time in measured.groupby(["hub", "time_band"], sort=True):
        if hub not in settings["hubs"] or band not in bands:
            continue
        for group, weekdays in _WEEKDAY_GROUPS.items():
            at_group = at_time.loc[at_time["weekday"].isin(weekdays)]
            # Product questions remain eligible when a band has enough observations
            # across lines but too few on any individual line.
            for field in ("arr_line", "arr_product"):
                for route, segment in at_group.groupby(field, sort=True):
                    if not route or len(segment) < FALLBACK_MIN_CONNECTIONS:
                        continue
                    # Fuzzy and official views have distinct measured cohorts. The
                    # official view uses resolved stop IDs, not pairwise feeder matches.
                    if arrivals is not None:
                        candidate = Question.model_validate(
                            {
                                "hub": hub,
                                "time_band": band,
                                "weekday_group": group,
                                "margin_min": settings["user_margins_minutes"][0],
                                field: route,
                            },
                            context={"study_config": config},
                        )
                        official, _ = _segment(candidate, arrivals, config)
                        if official.empty:
                            continue
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
    eligible_bands = (
        measured.loc[measured["hub"].isin(settings["hubs"])].groupby("time_band").size()
    )
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
        "strata_counts": [
            {"hub": hub, "time_band": band, "weekday_group": group, "margin_min": margin, "n": n}
            for (hub, band, group, margin), n in sorted(counts.items())
        ],
        "segments": segments,
        "versions": {"numpy": np.__version__, "pandas": pd.__version__},
    }
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
