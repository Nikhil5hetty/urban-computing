"""UC-012 quality report checks on ingested and schema-correct synthetic events."""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml

from tests.factories import stop_events, ts
from urban_computing.data.ingest import ingest_all
from urban_computing.data.quality import build_quality_report
from urban_computing.evaluation import invariants, registry

FIXTURE = Path("tests/fixtures/ist_sample")
CONFIG = Path("config/study.yaml")


def _config(tmp_path, raw_dir):
    config = yaml.safe_load(CONFIG.read_text())
    config["data"]["raw_dir"] = str(raw_dir)
    config["data"]["interim_dir"] = str(tmp_path / "interim")
    path = tmp_path / "study.yaml"
    path.write_text(yaml.safe_dump(config))
    return path, config


def test_fixture_report_and_cli(tmp_path):
    config, _ = _config(tmp_path, FIXTURE)
    interim = tmp_path / "interim"
    ingest_all(FIXTURE, interim / "ist")
    md = tmp_path / "report.md"
    js = interim / "quality.json"
    report = build_quality_report(interim, config, md, js)
    truth = json.loads((FIXTURE / "ground_truth.json").read_text())
    punctual = sum(s["delay_counts"]["under_3_min"] for s in truth["segments"])
    arrivals = punctual + sum(s["delay_counts"]["at_least_3_min"] for s in truth["segments"])
    assert report["I5"] == {
        "value": punctual / arrivals,
        "pass": False,
        "arrivals": arrivals,
        "punctual": punctual,
    }
    assert md.read_text().splitlines()[2].startswith("**I5 FAIL**")
    assert json.loads(js.read_text()) == report
    for key, count in truth["anomalies"].items():
        assert report["anomalies"][key] == count
    assert report["status_basis"] == "raw_blanks_recovered"
    coverage = {row["status"]: row["rows"] for row in report["arrival_status"]}
    assert coverage == {"": 32, "ESTIMATED": 1, "FORECAST": 1, "REAL": 32, "UNKNOWN": 1}
    assert report["low_real_coverage"] == [{"operator": "TEST", "rows": 67, "real_share": 32 / 67}]
    before = md.read_bytes(), js.read_bytes()
    result = subprocess.run(
        [sys.executable, "scripts/data_quality.py", "--config", str(config), "--out-md", str(md)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "I5 FAIL (16 of 32 arrivals punctual)" in result.stdout
    assert (md.read_bytes(), js.read_bytes()) == before


def test_filters_anomalies_and_dst(tmp_path):
    config, _ = _config(tmp_path, tmp_path / "missing-raw")
    interim = tmp_path / "interim"
    day = date(2026, 10, 25)
    planned = ts(day, "09:00")
    punctual = {"planned_arrival": planned, "actual_arrival": planned}
    first_fold = pd.Timestamp("2026-10-25T00:00:00Z").tz_convert("Europe/Zurich")
    second_fold = pd.Timestamp("2026-10-25T01:59:59Z").tz_convert("Europe/Zurich")
    after_fold = pd.Timestamp("2026-10-25T02:00:00Z").tz_convert("Europe/Zurich")
    events = stop_events(
        [
            *[{**punctual} for _ in range(4)],
            {**punctual, "actual_arrival": planned + pd.Timedelta(minutes=3)},
            {"operating_day": date(2026, 9, 30)},
            {"product": "Bus", "transport_text": " B|x "},
            {"additional_trip": True},
            {"pass_through": True},
            {
                "arrival_status": "FORECAST",
                "operator_abbr": "OTHER",
                "stop_name": " ",
                "planned_arrival": planned,
                "actual_arrival": planned + pd.Timedelta(hours=7),
                "planned_departure": planned,
                "actual_departure": first_fold,
            },
            {
                "planned_arrival": first_fold,
                "actual_arrival": second_fold,
                "planned_departure": second_fold,
            },
            {"planned_departure": after_fold, "operator_abbr": "OTHER", "arrival_status": "REAL"},
        ]
    )
    (interim / "ist").mkdir(parents=True)
    events.to_parquet(interim / "ist" / "events.parquet", index=False)
    report = build_quality_report(interim, config, tmp_path / "out.md", tmp_path / "out.json")
    assert [(r["filter"], r["before"], r["after"]) for r in report["filters"]] == [
        ("period", 12, 11),
        ("scope_products", 11, 10),
        ("exclude_additional_trips", 10, 9),
        ("exclude_pass_through", 9, 8),
        ("keep_status", 8, 7),
        ("measurable_real_arrival", 7, 5),
    ]
    assert report["I5"] == {"value": 0.8, "pass": True, "arrivals": 5, "punctual": 4}
    assert report["ambiguous_dst"] == [
        {"operator": "OTHER", "rows": 1},
        {"operator": "SBB", "rows": 1},
    ]
    assert report["anomalies"] == {
        "departure_before_arrival": 1,
        "departure_before_planned": 1,
        "arrival_over_6_hours": 1,
        "empty_stop_name": 1,
        "cancelled": 0,
        "pass_through": 1,
    }
    assert report["low_real_coverage"] == []  # OTHER is exactly at 50%.
    assert report["products"][0] == {"product": "Bus", "transport_text": " B|x ", "rows": 1}


def test_sample_invariant(tmp_path):
    _, config = _config(tmp_path, FIXTURE)
    provider = registry.INVARIANTS["I5"]
    assert provider.__module__ in registry.EXPERIMENT_MODULES
    assert provider is invariants.punctual_arrival_sanity
    context = registry.Context(
        config=config,
        sample=True,
        paths={"raw_dir": str(FIXTURE), "interim_dir": str(tmp_path / "interim")},
        seed=config["study"]["seed"],
    )
    result = provider(context)
    assert not result.passed
    assert result.details["value"] == pytest.approx(0.5)
