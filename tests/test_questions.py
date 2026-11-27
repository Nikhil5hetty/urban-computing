import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest
import yaml

from scripts import make_questions as cli
from tests import factories
from urban_computing.assistant.contract import Question
from urban_computing.assistant.crisp import crisp_answer
from urban_computing.assistant.engine import _p_miss
from urban_computing.evaluation.questions import _question_set, make_questions, write_questions
from urban_computing.fuzzy.vocabulary import load_vocabulary


@pytest.fixture
def study():
    return yaml.safe_load(Path("config/study.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def tables(study):
    pairs, arrivals = [], []
    for hub_index, hub in enumerate(study["connections"]["hubs"], 1):
        for band in ("early", "morning_peak", "evening"):
            for route in ("IC1", "IR16", "RE3"):
                # 2/20 are missed at all margins, including a cancelled departure.
                segment = factories.connections(
                    [None, -10.0, *([20.0] * 18), None],
                    hub=hub,
                    time_band=band,
                    arr_line=route,
                )
                segment.loc[20, "b_cancelled"] = False  # unknown gap
                ids = [f"{hub_index}-{band}-{route}-{index}" for index in range(len(segment))]
                segment["arr_journey_id"] = ids
                pairs.append(segment)
                arrivals.append(
                    factories.arrivals(
                        [0.0] * len(segment),
                        stop_id=f"850000{hub_index}00",
                        stop_name="A different display name",
                        time_band=band,
                        line=route,
                    ).assign(journey_id=ids)
                )
    # Same display name as a hub, but these rows belong to another stop.
    pairs.append(factories.connections([20.0] * 20, arr_line="wrong"))
    arrivals.append(
        factories.arrivals([0.0] * 20, stop_id="9999999", line="wrong").assign(
            journey_id=[f"A{index}" for index in range(20)]
        )
    )
    return pd.concat(pairs, ignore_index=True), pd.concat(arrivals, ignore_index=True)


def test_stratification_and_determinism(tables, study, tmp_path):
    pairs, _ = tables
    pairs = pairs.loc[pairs["arr_line"].ne("wrong")]
    seed = study["study"]["seed"]
    questions = make_questions(pairs, study, seed)
    assert len(questions) >= 120
    assert {q.hub for q in questions} == set(study["connections"]["hubs"])
    assert {q.time_band for q in questions} == {"early", "morning_peak", "evening"}
    assert {q.margin_min for q in questions} == set(study["connections"]["user_margins_minutes"])
    strata = {(q.hub, q.time_band, q.weekday_group, q.margin_min) for q in questions}
    assert len(strata) == 3 * 3 * 3 * 6
    keys = [q.model_dump_json(exclude={"question_id"}) for q in questions]
    assert len(keys) == len(set(keys))

    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    write_questions(questions, first)
    write_questions(make_questions(pairs.sample(frac=1, random_state=4), study, seed), second)
    assert first.read_bytes() == second.read_bytes()
    assert make_questions(pairs, study, seed + 1) != questions
    assert [Question.model_validate_json(line) for line in first.read_text().splitlines()] == (
        questions
    )

    vocab = load_vocabulary()
    borderline = 0
    for question in questions:
        p_miss, n, fallback, _, _ = _p_miss(question, pairs, pd.DataFrame(), vocab, study)
        assert n in (20, 60)
        assert not fallback
        borderline += abs(p_miss - 0.075) <= 0.05 or abs(p_miss - 0.25) <= 0.05
    assert borderline >= 15


def test_rejects_insufficient_observations(study):
    pairs = factories.connections([20.0] * 19 + [None], b_cancelled=False)
    with pytest.raises(ValueError, match="Insufficient eligible segments"):
        make_questions(pairs, study, 0)


def test_rejects_missing_borderline_quota(tables, study):
    pairs, _ = tables
    pairs = pairs.assign(actual_gap_min=20.0, b_cancelled=False)
    with pytest.raises(ValueError, match="Need 15 borderline questions, found 0"):
        make_questions(pairs, study, 0)


@pytest.mark.parametrize("mixed_ids", [False, True])
def test_cli_writes_question_set_and_manifest(tables, study, tmp_path, monkeypatch, mixed_ids):
    pairs, arrivals = tables
    if mixed_ids:
        # UC-014 can resolve these feeders by SLOID while ARRIVALS keeps the
        # alternate BPUIC. Losing a feeder from the official cohort must not
        # remove a measured connection from the fuzzy cohort.
        first = arrivals.groupby(["stop_id", "time_band", "line"]).head(1).index
        arrivals.loc[first, "stop_id"] = "9999998"
    ids = {hub: [f"850000{i}"] for i, hub in enumerate(study["connections"]["hubs"], 1)}

    def resolve(atlas_path, hubs):
        assert atlas_path.name == "actual-date-swiss-service-point.csv"
        assert hubs == study["connections"]["hubs"]
        return ids

    monkeypatch.setattr(cli.connection_data, "_hub_ids", resolve)
    study["data"]["processed_dir"] = str(tmp_path)
    config = tmp_path / "study.yaml"
    config.write_text(yaml.safe_dump(study), encoding="utf-8")
    pairs.to_parquet(tmp_path / "connections.parquet", index=False)
    arrivals.to_parquet(tmp_path / "arrivals.parquet", index=False)
    output = tmp_path / "eval" / "questions.jsonl"
    monkeypatch.setattr(
        sys, "argv", ["make_questions.py", "--config", str(config), "--output", str(output)]
    )
    cli.main()
    manifest_path = output.with_name("questions_manifest.json")
    manifest = json.loads(manifest_path.read_bytes())
    questions = [Question.model_validate_json(line) for line in output.read_text().splitlines()]
    assert manifest["seed"] == study["study"]["seed"]
    assert manifest["n_questions"] == len(questions) >= 120
    assert manifest["n_borderline"] == len(questions)
    assert {q.question_id for q in questions} == set(manifest["segments"])
    assert {segment["n"] for segment in manifest["segments"].values()} <= {20, 60, 80}
    assert all(q.arr_line != "wrong" for q in questions)
    expected = Counter((q.hub, q.time_band, q.weekday_group, q.margin_min) for q in questions)
    assert {
        (s["hub"], s["time_band"], s["weekday_group"], s["margin_min"]): s["n"]
        for s in manifest["strata_counts"]
    } == expected
    for question in questions:
        crisp_answer(
            question,
            arrivals,
            {
                **study,
                "connections": {
                    **study["connections"],
                    "hub_stop_ids": ids,
                },
            },
        )
        _, n, fallback, _, _ = _p_miss(question, pairs, arrivals, load_vocabulary(), study)
        assert n == manifest["segments"][question.question_id]["n"]
        assert not fallback
    before = output.read_bytes(), manifest_path.read_bytes()
    cli.main()
    assert before == (output.read_bytes(), manifest_path.read_bytes())


@pytest.mark.parametrize(
    "field,value",
    [
        ("stop_id", "9999998"),
        ("time_band", "outside"),
        ("weekday", 6),
        ("line", "other"),
        ("cancelled", True),
        ("delay_min", float("nan")),
    ],
)
def test_excludes_candidates_without_measured_official_cohort(tables, study, field, value):
    pairs, arrivals = tables
    study["connections"]["hub_stop_ids"] = {
        hub: [f"850000{i}"] for i, hub in enumerate(study["connections"]["hubs"], 1)
    }
    arrivals.loc[arrivals["line"].eq("IC1"), field] = value
    questions, _ = _question_set(pairs, study, study["study"]["seed"], arrivals=arrivals)
    assert questions
    assert all(
        q.arr_line != "IC1" or (field == "weekday" and q.weekday_group == "all") for q in questions
    )
    assert any(q.arr_line == "IR16" for q in questions)


def test_mixed_identifiers_from_real_builders(study):
    from datetime import date, timedelta

    from urban_computing.data.arrivals import build_arrivals
    from urban_computing.data.connections import build_connections

    hub = "Zürich HB"
    study["connections"]["hubs"] = [hub]
    ids = {hub: ["8503000", "ch:1:sloid:3000"]}
    study["connections"]["hub_stop_ids"] = ids
    rows = []
    for day_index in range(28):
        day = date(2026, 10, 1) + timedelta(days=day_index)
        for hour in (4, 7, 19):
            for route_index, route in enumerate(("IC1", "IR16", "RE3")):
                planned = factories.ts(day, f"{hour:02d}:{route_index * 20:02d}")
                base = {
                    "operating_day": day,
                    "stop_id": "8503000",
                    "sloid": "ch:1:sloid:3000",
                    "stop_name": hub,
                }
                rows.append(
                    {
                        **base,
                        "journey_id": f"A-{day}-{hour}-{route}",
                        "line": route,
                        "stop_id": "9999998" if day_index == 0 else "8503000",
                        "planned_arrival": planned,
                        "actual_arrival": planned + timedelta(minutes=14 if day_index < 3 else 0),
                    }
                )
                rows.append(
                    {
                        **base,
                        "journey_id": f"B-{day}-{hour}-{route}",
                        "line": "S1",
                        "planned_departure": planned + timedelta(minutes=4),
                        "actual_departure": planned + timedelta(minutes=4),
                    }
                )
    events = factories.stop_events(rows)
    atlas = pd.DataFrame(
        [
            {
                "number": "8503000",
                "sloid": "ch:1:sloid:3000",
                "isoCountryCode": "CH",
                "cantonAbbreviation": "ZH",
            }
        ]
    )
    arrivals = build_arrivals(events, atlas, study)
    pairs = build_connections(events, ids, study)
    assert arrivals["stop_id"].eq("9999998").any()
    questions, manifest = _question_set(pairs, study, study["study"]["seed"], arrivals=arrivals)
    assert len(questions) >= 120
    for question in questions:
        crisp_answer(question, arrivals, study)
        _, n, fallback, _, _ = _p_miss(question, pairs, arrivals, load_vocabulary(), study)
        assert not fallback
        assert n == manifest["segments"][question.question_id]["n"]
