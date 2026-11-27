"""Verify the methodological baseline through the project evaluation runner."""

import csv
import shutil
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from tests.factories import arrivals
from urban_computing.evaluation import baseline
from urban_computing.evaluation.run import run

ROOT = Path(__file__).resolve().parents[1]
QUANTIFIERS = ("few", "about_half", "most")
SUMMARIZERS = ("on_time", "slightly_late", "late", "very_late")


@pytest.mark.parametrize("second_delays", [[2], [None]])
def test_baseline_tables(tmp_path, monkeypatch, second_delays):
    for directory in ("config", "eval", "tests/fixtures/ist_sample"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    monkeypatch.chdir(tmp_path)

    def fixture_arrivals(stop_events, service_points, config):
        assert not stop_events.empty
        return pd.concat(
            [
                arrivals([0] * 7 + [6] * 18 + [None]),
                arrivals(second_delays, operating_day=date(2026, 10, 20), line="IR16"),
            ],
            ignore_index=True,
        )

    monkeypatch.setattr(baseline, "build_arrivals", fixture_arrivals)
    result = run(Path("config/study.yaml"), sample=True, only="baseline")
    tables = result["tables"]
    names = ("baseline_pincay", "baseline_pincay_first", "baseline_pincay_second")
    assert tables == {name: f"tables/{name}.csv" for name in names}
    by_pair = {}
    for name, path in tables.items():
        with (Path("results") / path).open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            assert reader.fieldnames == ["quantifier", "summarizer", "truth", "valid"]
            rows = {(row["quantifier"], row["summarizer"]): row for row in reader}
            assert list(rows) == [(q, s) for q in QUANTIFIERS for s in SUMMARIZERS]
            assert reader.line_num == 13
            by_pair[name] = rows

    first = by_pair["baseline_pincay_first"]
    # Fuzzy proportions of 0.28 and 0.72 produce truth 0.6 on the paper's ramps.
    for pair in (("few", "on_time"), ("most", "late")):
        assert float(first[pair]["truth"]) == pytest.approx(0.6)
        assert first[pair]["valid"] == "True"
    assert float(first["about_half", "on_time"]["truth"]) == pytest.approx(0.4)
    assert first["about_half", "on_time"]["valid"] == "False"

    second = by_pair["baseline_pincay_second"]
    combined = by_pair["baseline_pincay"]
    if second_delays == [None]:
        assert all(row["truth"] == "" and row["valid"] == "False" for row in second.values())
        assert combined == first
    else:
        assert second["about_half", "on_time"]["truth"] == "1.0"
        assert second["about_half", "slightly_late"]["truth"] == "1.0"
        assert float(combined["few", "on_time"]["truth"]) == pytest.approx((0.4 - 7.5 / 26) / 0.2)
        assert combined["few", "on_time"]["valid"] == "False"
