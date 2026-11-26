"""Small, reproducible Ist-Daten v2 fixtures with analytical ground truth."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from random import Random

# Header order follows the publisher's v2 cookbook example.
_COLUMNS = (
    "_id",
    "BETRIEBSTAG",
    "FAHRT_BEZEICHNER",
    "BETREIBER_ID",
    "BETREIBER_ABK",
    "BETREIBER_NAME",
    "PRODUKT_ID",
    "LINIEN_ID",
    "LINIEN_TEXT",
    "UMLAUF_ID",
    "VERKEHRSMITTEL_TEXT",
    "ZUSATZFAHRT_TF",
    "FAELLT_AUS_TF",
    "BPUIC",
    "HALTESTELLEN_NAME",
    "ANKUNFTSZEIT",
    "AN_PROGNOSE",
    "AN_PROGNOSE_STATUS",
    "ABFAHRTSZEIT",
    "AB_PROGNOSE",
    "AB_PROGNOSE_STATUS",
    "DURCHFAHRT_TF",
    "SLOID",
)
_ZURICH = ("Zürich HB", "8503000", "ch:1:sloid:3000")
_OLTEN = ("Olten", "8500218", "ch:1:sloid:218")


def _event(
    start: datetime,
    journey: str,
    hub: tuple[str, str, str],
    line: str,
    **fields: str,
) -> dict[str, str]:
    name, bpuic, sloid = hub
    return {
        "BETRIEBSTAG": f"{start.day}.{start.month}.{start.year}",
        "FAHRT_BEZEICHNER": journey,
        "BETREIBER_ID": "85:fixture",
        "BETREIBER_ABK": "TEST",
        "BETREIBER_NAME": "Synthetic operator",
        "PRODUKT_ID": "Zug",
        "LINIEN_ID": line,
        "LINIEN_TEXT": line,
        "VERKEHRSMITTEL_TEXT": "IC" if line == "IC1" else "S",
        "BPUIC": bpuic,
        "HALTESTELLEN_NAME": name,
        "SLOID": sloid,
        **fields,
    }


def _time(value: datetime, *, actual: bool = False) -> str:
    return value.strftime("%d.%m.%Y %H:%M:%S" if actual else "%d.%m.%Y %H:%M")


def generate(out_dir: Path, seed: int = 20261126, separator: str = ";") -> Path:
    """Write three daily CSVs and their ground-truth JSON into out_dir.

    Seed controls the assignment of delays to departures. Separator is a one-character
    CSV delimiter. Ground truth expresses delays and connection gaps in minutes.
    Return the directory written.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    random = Random(seed)
    segments = [
        (_ZURICH, "IC1", "S3", "morning_peak", 6, [0] * 12 + [3] * 13),
        (_OLTEN, "S3", "S9", "midday", 11, [-1, 1, 2, 4, 6, 10]),
    ]
    daily: list[list[dict[str, str]]] = [[], [], []]
    truth_segments = []
    connections = []
    for hub, arr_line, dep_line, time_band, hour, delays in segments:
        random.shuffle(delays)
        truth_segments.append(
            {
                "hub": hub[0],
                "line": arr_line,
                "time_band": time_band,
                "delay_counts": {
                    "under_3_min": sum(delay < 3 for delay in delays),
                    "at_least_3_min": sum(delay >= 3 for delay in delays),
                },
            }
        )
        for index, delay in enumerate(delays):
            slot, day = divmod(index, 3)
            start = datetime(2026, 10, 1 + day, hour) + timedelta(minutes=20 * slot)
            arr_id, dep_id = (f"fixture:{arr_line}:{index}:{side}" for side in ("A", "B"))
            gap = 4 if hub == _ZURICH else (1, 2, 4, 15, 16, 4)[index]
            dep = start + timedelta(minutes=gap)
            cancelled = hub == _OLTEN and index == 5
            daily[day].extend(
                (
                    _event(
                        start,
                        arr_id,
                        hub,
                        arr_line,
                        ANKUNFTSZEIT=_time(start),
                        AN_PROGNOSE=_time(start + timedelta(minutes=delay), actual=True),
                        AN_PROGNOSE_STATUS="REAL",
                    ),
                    _event(
                        start,
                        dep_id,
                        hub,
                        dep_line,
                        ABFAHRTSZEIT=_time(dep),
                        AB_PROGNOSE="" if cancelled else _time(dep, actual=True),
                        AB_PROGNOSE_STATUS="" if cancelled else "REAL",
                        FAELLT_AUS_TF="true" if cancelled else "",
                    ),
                )
            )
            if 2 <= gap <= 15:
                connections.append(
                    {
                        "hub": hub[0],
                        "operating_day": start.date().isoformat(),
                        "arr_journey_id": arr_id,
                        "dep_journey_id": dep_id,
                        "planned_gap_min": gap,
                        "actual_gap_min": None if cancelled else gap - delay,
                        "b_cancelled": cancelled,
                    }
                )

    for index, status in enumerate(("ESTIMATED", "FORECAST", "UNKNOWN")):
        start = datetime(2026, 10, 1 + index, 19)
        daily[index].append(
            _event(
                start,
                f"fixture:forecast:{index}",
                _OLTEN,
                "S9",
                ANKUNFTSZEIT=_time(start),
                AN_PROGNOSE=_time(start, actual=True),
                AN_PROGNOSE_STATUS=status,
            )
        )
    start = datetime(2026, 10, 1, 21)
    daily[0].extend(
        (
            _event(start, "fixture:pass", _ZURICH, "IC1", DURCHFAHRT_TF="true"),
            _event(
                start,
                "fixture:order",
                _OLTEN,
                "S9",
                ANKUNFTSZEIT=_time(start),
                AN_PROGNOSE=_time(start, actual=True),
                AN_PROGNOSE_STATUS="REAL",
                ABFAHRTSZEIT=_time(start + timedelta(minutes=1)),
                AB_PROGNOSE=_time(start - timedelta(minutes=1), actual=True),
                AB_PROGNOSE_STATUS="REAL",
            ),
        )
    )
    for day, rows in enumerate(daily, start=1):
        with (out_dir / f"2026-10-{day:02}_IstDaten.csv").open(
            "w", encoding="utf-8", newline=""
        ) as fh:
            writer = csv.DictWriter(
                fh, fieldnames=_COLUMNS, delimiter=separator, lineterminator="\n"
            )
            writer.writeheader()
            for index, row in enumerate(rows, start=1):
                writer.writerow({"_id": str(index), **row})

    # Keep the isolated anomaly in the ground-truth arrival population.
    truth_segments.append(
        {
            "hub": "Olten",
            "line": "S9",
            "time_band": "evening",
            "delay_counts": {"under_3_min": 1, "at_least_3_min": 0},
        }
    )
    truth = {
        "segments": truth_segments,
        "connections": connections,
        "anomalies": {"departure_before_arrival": 1, "cancelled": 1, "pass_through": 1},
    }
    (out_dir / "ground_truth.json").write_text(
        json.dumps(truth, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return out_dir
