"""Validate the generated Ist-Daten fixture independently of its generator."""

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from urban_computing.data.synthetic import generate

_COMMITTED = Path(__file__).parent / "fixtures" / "ist_sample"
_HEADER = (
    "_id BETRIEBSTAG FAHRT_BEZEICHNER BETREIBER_ID BETREIBER_ABK BETREIBER_NAME "
    "PRODUKT_ID LINIEN_ID LINIEN_TEXT UMLAUF_ID VERKEHRSMITTEL_TEXT ZUSATZFAHRT_TF "
    "FAELLT_AUS_TF BPUIC HALTESTELLEN_NAME ANKUNFTSZEIT AN_PROGNOSE AN_PROGNOSE_STATUS "
    "ABFAHRTSZEIT AB_PROGNOSE AB_PROGNOSE_STATUS DURCHFAHRT_TF SLOID"
).split()


def _files(path):
    return {p.name: p.read_bytes() for p in path.iterdir()}


def test_fixture_is_reproducible(tmp_path):
    first = _files(generate(tmp_path / "first"))
    assert first == _files(generate(tmp_path / "second")) == _files(_COMMITTED)
    assert first != _files(generate(tmp_path / "third", seed=1))
    assert sum(map(len, first.values())) <= 200_000


def _read(path, separator):
    rows = []
    files = sorted(path.glob("*.csv"))
    assert len(files) == 3
    for day, file in enumerate(files, 1):
        with file.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh, delimiter=separator)
            assert reader.fieldnames == _HEADER
            for row in reader:
                assert row["BETRIEBSTAG"] == f"{day}.10.2026"
                for column, fmt in (
                    ("ANKUNFTSZEIT", "%d.%m.%Y %H:%M"),
                    ("ABFAHRTSZEIT", "%d.%m.%Y %H:%M"),
                    ("AN_PROGNOSE", "%d.%m.%Y %H:%M:%S"),
                    ("AB_PROGNOSE", "%d.%m.%Y %H:%M:%S"),
                ):
                    value = row[column]
                    row[column] = datetime.strptime(value, fmt) if value else None
                    assert not value or row[column].strftime(fmt) == value
                rows.append(row)
    return rows


def test_schema_and_separator(tmp_path):
    rows = _read(generate(tmp_path, separator=","), ",")
    assert {r["HALTESTELLEN_NAME"] for r in rows} == {"Zürich HB", "Olten"}
    assert {r["LINIEN_TEXT"] for r in rows} == {"IC1", "S3", "S9"}
    assert {r["VERKEHRSMITTEL_TEXT"] for r in rows} == {"IC", "S"}
    assert {r["AN_PROGNOSE_STATUS"] for r in rows} == {
        "REAL",
        "ESTIMATED",
        "FORECAST",
        "UNKNOWN",
        "",
    }


def _minutes(later, earlier):
    return (later - earlier).total_seconds() / 60


def test_ground_truth_matches_events():
    rows = _read(_COMMITTED, ";")
    truth = json.loads((_COMMITTED / "ground_truth.json").read_text(encoding="utf-8"))
    arrivals = [r for r in rows if r["AN_PROGNOSE_STATUS"] == "REAL"]
    bands = {6: "morning_peak", 7: "morning_peak", 8: "morning_peak", 11: "midday", 21: "evening"}
    counts = defaultdict(lambda: {"under_3_min": 0, "at_least_3_min": 0})
    borderline = []
    for row in arrivals:
        start = row["ANKUNFTSZEIT"]
        key = (row["HALTESTELLEN_NAME"], row["LINIEN_TEXT"], bands[start.hour])
        delay = _minutes(row["AN_PROGNOSE"], start)
        counts[key]["under_3_min" if delay < 3 else "at_least_3_min"] += 1
        if key == ("Zürich HB", "IC1", "morning_peak"):
            borderline.append(delay)

    assert counts == {
        (s["hub"], s["line"], s["time_band"]): s["delay_counts"] for s in truth["segments"]
    }
    assert Counter(borderline) == {0: 12, 3: 13}
    # At a 4-minute margin with spread 2, the 3-minute delays have membership 0.5.
    assert (13 * 0.5 / 25) < 0.5 < (13 / 25)
    assert truth["anomalies"] == {
        "cancelled": sum(r["FAELLT_AUS_TF"] == "true" for r in rows),
        "pass_through": sum(r["DURCHFAHRT_TF"] == "true" for r in rows),
        "departure_before_arrival": sum(
            r["AB_PROGNOSE"] < r["AN_PROGNOSE"]
            for r in rows
            if r["AB_PROGNOSE"] and r["AN_PROGNOSE"]
        ),
    }
    assert truth["anomalies"] == dict.fromkeys(truth["anomalies"], 1)

    pairs = {}
    for arr in arrivals:
        for dep in rows:
            if (
                not dep["ABFAHRTSZEIT"]
                or dep["HALTESTELLEN_NAME"] != arr["HALTESTELLEN_NAME"]
                or dep["FAHRT_BEZEICHNER"] == arr["FAHRT_BEZEICHNER"]
            ):
                continue
            gap = _minutes(dep["ABFAHRTSZEIT"], arr["ANKUNFTSZEIT"])
            cancelled = dep["FAELLT_AUS_TF"] == "true"
            if 2 <= gap <= 15 and (cancelled or dep["AB_PROGNOSE_STATUS"] == "REAL"):
                key = (arr["FAHRT_BEZEICHNER"], dep["FAHRT_BEZEICHNER"])
                pairs[key] = (
                    arr["HALTESTELLEN_NAME"],
                    arr["ANKUNFTSZEIT"].date().isoformat(),
                    gap,
                    None if cancelled else _minutes(dep["AB_PROGNOSE"], arr["AN_PROGNOSE"]),
                    cancelled,
                )
    assert len(pairs) == len(truth["connections"]) == 29
    assert pairs == {
        (c["arr_journey_id"], c["dep_journey_id"]): (
            c["hub"],
            c["operating_day"],
            c["planned_gap_min"],
            c["actual_gap_min"],
            c["b_cancelled"],
        )
        for c in truth["connections"]
    }
