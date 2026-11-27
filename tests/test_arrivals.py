"""Exercise UC-013 through its file entry point with synthetic stop events."""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml

from tests.factories import DEFAULT_DAY, stop_events, ts
from urban_computing.data.arrivals import build_arrivals
from urban_computing.data.quality import build_quality_report

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def inputs():
    config = yaml.safe_load((ROOT / "config/study.yaml").read_text())
    planned = ts(DEFAULT_DAY, "06:00")
    earlier = ts(DEFAULT_DAY, "05:59", 30)
    later = ts(DEFAULT_DAY, "06:00", 30)
    boundary = ts(DEFAULT_DAY, "09:00")
    sunday = date(2026, 10, 25)
    folds = pd.to_datetime(["2026-10-25T00:00Z", "2026-10-25T01:00Z"], utc=True)
    outside_dst = ts(sunday, "03:00")
    base = {"planned_arrival": planned, "actual_arrival": later}
    variants = {
        "early": {"planned_arrival": earlier, "actual_arrival": earlier},
        "positive": {"sloid": None, "stop_id": "850021802"},
        "negative": {"actual_arrival": earlier, "stop_id": "ch:1:sloid:218:1:2", "sloid": None},
        "midday": {"planned_arrival": boundary, "actual_arrival": boundary},
        "cancelled": {"cancelled": True},
        "cancelled_forecast": {
            "cancelled": True,
            "arrival_status": "FORECAST",
            "actual_arrival": pd.NaT,
        },
        "planned_fold": {
            "operating_day": sunday,
            "planned_arrival": folds[0].tz_convert("Europe/Zurich"),
            "actual_arrival": outside_dst,
        },
        "actual_fold": {
            "operating_day": sunday,
            "planned_arrival": outside_dst,
            "actual_arrival": folds[1].tz_convert("Europe/Zurich"),
        },
        "after_fold": {
            "operating_day": sunday,
            "planned_arrival": outside_dst,
            "actual_arrival": outside_dst,
        },
        "unmatched": {"sloid": None, "stop_id": "8509999"},
        "foreign": {"sloid": "ch:1:sloid:9998", "stop_id": "8509998"},
        "unmatched_foreign": {"sloid": None, "stop_id": "800123400"},
        "missing_planned": {"planned_arrival": pd.NaT},
        "missing_actual": {"actual_arrival": pd.NaT},
        "out_of_period": {"operating_day": date(2026, 9, 30)},
        "bus": {"product": "Bus"},
        "extra": {"additional_trip": True},
        "passing": {"pass_through": True},
        "forecast": {"arrival_status": "FORECAST"},
    }
    events = stop_events(
        [{**base, **override, "journey_id": name} for name, override in variants.items()]
    )
    points = pd.DataFrame(
        {
            "sloid": ["ch:1:sloid:218", "ch:1:sloid:9998"],
            "number": ["8500218", "8509998"],
            "isoCountryCode": ["CH", "DE"],
            "cantonAbbreviation": ["SO", ""],
        }
    )
    return events, points, config


def test_arrivals_rules(inputs):
    result = build_arrivals(*inputs).set_index("journey_id")
    assert result.index.tolist() == [
        "early",
        "positive",
        "negative",
        "midday",
        "cancelled",
        "cancelled_forecast",
        "planned_fold",
        "actual_fold",
        "after_fold",
        "unmatched",
    ]
    assert result.loc[["early", "positive", "midday"], "time_band"].tolist() == [
        "early",
        "morning_peak",
        "midday",
    ]
    assert result.loc[["positive", "negative", "after_fold"], "delay_min"].tolist() == [
        0.5,
        -0.5,
        0.0,
    ]
    assert result.loc[["cancelled", "cancelled_forecast"], "cancelled"].all()
    assert result.loc[["cancelled", "cancelled_forecast"], "actual_arrival"].isna().all()
    assert (
        result.loc[["cancelled", "cancelled_forecast", "planned_fold", "actual_fold"], "delay_min"]
        .isna()
        .all()
    )
    assert result.loc[["positive", "negative"], "canton"].tolist() == ["SO", "SO"]
    assert pd.isna(result.loc["unmatched", "canton"])
    assert result.loc[["positive", "planned_fold"], "weekday"].tolist() == [0, 6]
    assert result.loc[["positive", "planned_fold"], "half"].tolist() == ["first", "second"]


def test_cli_log_and_i5(tmp_path, inputs):
    events, points, config = inputs
    interim = tmp_path / "interim"
    ist = interim / "ist"
    ist.mkdir(parents=True)
    events.to_parquet(ist / "sample.parquet", index=False)
    atlas_dir = tmp_path / "atlas"
    atlas_dir.mkdir()
    points.to_csv(atlas_dir / "actual-date-swiss-service-point.csv", sep=";", index=False)
    config["data"].update(
        interim_dir="interim",
        processed_dir="processed",
        service_points_dir="atlas",
        raw_dir="unused",
    )
    config_path = tmp_path / "config" / "study.yaml"
    config_path.parent.mkdir()
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/build_arrivals.py")],
        cwd=tmp_path,
        check=True,
    )
    output = tmp_path / "processed"
    result = pd.read_parquet(output / "arrivals.parquet")
    log = json.loads((output / "arrivals_log.json").read_text())
    assert (log["rows_in"], log["rows_out"]) == (19, 10)
    assert [stage["after"] for stage in log["filters"]] == [18, 17, 16, 15, 14, 12]
    assert log["ambiguous_dst_rows"] == 2
    assert log["foreign_rows_excluded"] == 2
    assert (log["unmatched_rows"], log["unmatched_share"]) == (1, 0.1)
    quality = build_quality_report(
        interim,
        config_path,
        tmp_path / "quality.md",
        tmp_path / "quality.json",
    )
    assert quality["I5"]["arrivals"] == log["i5_measurable_before_geographic_filter"] == 8
    assert result["delay_min"].count() == 6

    # I5 has no geographic filter. Compare the table on the same Swiss-only input.
    swiss = events.loc[~events["journey_id"].isin(["foreign", "unmatched_foreign"])]
    swiss.to_parquet(ist / "sample.parquet", index=False)
    quality = build_quality_report(
        interim,
        config_path,
        tmp_path / "quality.md",
        tmp_path / "quality.json",
    )
    assert result["delay_min"].count() == quality["I5"]["arrivals"]
    assert (result["delay_min"] < 3).sum() == quality["I5"]["punctual"]
