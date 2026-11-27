"""Fixture-based checks for UC-014, independent of the upstream data producers."""

import csv
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml

from tests.factories import DEFAULT_DAY, assert_schema, stop_events, ts
from urban_computing.data.connections import build_connections
from urban_computing.data.schemas import CONNECTIONS, NULLABLE, TZ

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/ist_sample"
CONFIG = ROOT / "config/study.yaml"
HUB_IDS = {
    "Zürich HB": ["8503000", "ch:1:sloid:3000"],
    "Bern": ["8507000", "ch:1:sloid:7000"],
    "Olten": ["8500218", "ch:1:sloid:218"],
}


@pytest.fixture
def config():
    return yaml.safe_load(CONFIG.read_text())


def _timestamp(value):
    if not value:
        return pd.NaT
    return pd.Timestamp(
        datetime.strptime(value, "%d.%m.%Y %H:%M:%S" if len(value) > 16 else "%d.%m.%Y %H:%M"),
        tz=TZ,
    )


def _sample_events():
    rows = []
    for path in sorted(FIXTURE.glob("*.csv")):
        with path.open(encoding="utf-8", newline="") as source:
            for row in csv.DictReader(source, delimiter=";"):
                rows.append(
                    {
                        "operating_day": datetime.strptime(row["BETRIEBSTAG"], "%d.%m.%Y").date(),
                        "journey_id": row["FAHRT_BEZEICHNER"],
                        "stop_id": row["BPUIC"],
                        "sloid": row["SLOID"],
                        "stop_name": row["HALTESTELLEN_NAME"],
                        "product": row["PRODUKT_ID"],
                        "line": row["LINIEN_TEXT"],
                        "planned_arrival": _timestamp(row["ANKUNFTSZEIT"]),
                        "actual_arrival": _timestamp(row["AN_PROGNOSE"]),
                        "arrival_status": row["AN_PROGNOSE_STATUS"],
                        "planned_departure": _timestamp(row["ABFAHRTSZEIT"]),
                        "actual_departure": _timestamp(row["AB_PROGNOSE"]),
                        "departure_status": row["AB_PROGNOSE_STATUS"],
                        "cancelled": row["FAELLT_AUS_TF"].lower() == "true",
                        "pass_through": row["DURCHFAHRT_TF"].lower() == "true",
                    }
                )
    return stop_events(rows)


def test_fixture_ground_truth(config):
    result = build_connections(_sample_events(), HUB_IDS, config)
    assert_schema(result, CONNECTIONS)
    expected = pd.DataFrame(json.loads((FIXTURE / "ground_truth.json").read_text())["connections"])
    key = ["arr_journey_id", "dep_journey_id"]
    result["operating_day"] = result["operating_day"].astype(str)
    pd.testing.assert_frame_equal(
        result[list(expected)].sort_values(key).reset_index(drop=True),
        expected.sort_values(key).reset_index(drop=True),
        check_dtype=False,
    )


def test_through_trains_and_boundaries(config):
    arrival = ts(DEFAULT_DAY, "08:59")
    options = [
        ("too_short", 1, {}),
        ("lower", 2, {"stop_id": "850021802", "sloid": None}),
        ("upper", 15, {"stop_id": "", "sloid": "ch:1:sloid:218:1:2"}),
        ("too_long", 16, {}),
        ("wrong_stop", 3, {"stop_id": "8500000", "sloid": None}),
        ("forecast", 4, {"departure_status": "FORECAST"}),
        ("missing", 5, {"actual_departure": pd.NaT}),
        ("passing", 6, {"pass_through": True}),
        ("extra", 7, {"additional_trip": True}),
        ("cancelled", 8, {"cancelled": True}),
    ]
    result = build_connections(
        stop_events(
            [
                {
                    "journey_id": "A",
                    "planned_arrival": arrival,
                    "actual_arrival": arrival + timedelta(seconds=30),
                    "planned_departure": arrival + timedelta(minutes=4),
                    "actual_departure": arrival + timedelta(minutes=4),
                    "stop_name": "Unrelated label",
                },
                *[
                    {
                        "journey_id": name,
                        "planned_arrival": arrival - timedelta(minutes=30),
                        "planned_departure": arrival + timedelta(minutes=gap),
                        "actual_departure": arrival + timedelta(minutes=gap, seconds=15),
                        **overrides,
                    }
                    for name, gap, overrides in options
                ],
            ]
        ),
        HUB_IDS,
        config,
    )
    assert set(result["arr_journey_id"]) == {"A"}
    assert set(result["dep_journey_id"]) == {"lower", "upper", "cancelled"}
    result = result.set_index("dep_journey_id").loc[["lower", "upper", "cancelled"]]
    assert result["planned_gap_min"].tolist() == [2, 15, 8]
    assert result["actual_gap_min"].iloc[:2].tolist() == [1.75, 14.75]
    assert result["dep_delay_min"].iloc[:2].tolist() == [0.25, 0.25]
    assert result["arr_delay_min"].tolist() == [0.5] * 3
    assert result["b_cancelled"].tolist() == [False, False, True]
    assert result.loc["cancelled", ["actual_gap_min", "dep_delay_min"]].isna().all()
    assert result["time_band"].tolist() == ["morning_peak"] * 3
    assert result["weekday"].tolist() == [0] * 3
    assert result["half"].tolist() == ["first"] * 3


def test_cli_and_daily_counts(tmp_path, config):
    ist = tmp_path / "ist"
    ist.mkdir()
    events = _sample_events()
    for day, daily_events in events.groupby("operating_day"):
        daily_events.to_parquet(ist / f"{day}.parquet", index=False)
    atlas = tmp_path / "atlas.csv"
    atlas.write_text(
        "designationOfficial;isoCountryCode;number;sloid\n"
        + "".join(f"{name};CH;{ids[0]};{ids[1]}\n" for name, ids in HUB_IDS.items())
        + "Bern;DE;8000001;\n",
        encoding="utf-8",
    )
    output = tmp_path / "processed" / "connections.parquet"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/build_connections.py"),
            "--config",
            str(CONFIG),
            "--interim-dir",
            str(tmp_path),
            "--service-points",
            str(atlas),
            "--out",
            str(output),
        ],
        check=True,
    )
    types = {
        "str": pa.string(),
        "date": pa.date32(),
        "float": pa.float64(),
        "int": pa.int64(),
        "bool": pa.bool_(),
    }
    assert [(field.name, field.type) for field in pq.read_schema(output)] == [
        (name, types[kind]) for name, kind in CONNECTIONS.items()
    ]
    expected = build_connections(events, HUB_IDS, config)
    actual = pd.read_parquet(output)
    assert set(actual.columns[actual.isna().any()]) == NULLABLE["CONNECTIONS"]
    actual["operating_day"] = pd.to_datetime(actual["operating_day"]).dt.date
    pd.testing.assert_frame_equal(actual, expected)
    hubs = json.loads(output.with_name("connections_log.json").read_text())["hubs"]
    assert hubs["Bern"]["real_share"] is None
    assert hubs["Olten"]["matched_ids"] == HUB_IDS["Olten"]
    assert hubs["Olten"]["by_day"]["2026-10-03"] == {"candidate_pairs": 2, "pairs": 2}
    assert hubs["Olten"]["candidate_pairs"] == 4
    assert hubs["Olten"]["real_share"] == 0.75
    assert sum(hub["pairs"] for hub in hubs.values()) == len(expected)
