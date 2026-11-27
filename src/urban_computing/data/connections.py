"""Reconstruct hub transfers from STOP_EVENTS (UC-014)."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import pandas as pd
import yaml

from urban_computing.data.schemas import CONNECTIONS, TZ


def _local_minute(hhmm: str) -> int:
    hour, minute = map(int, hhmm.split(":"))
    return hour * 60 + minute


def _stop_key(column: str) -> str:
    # Collapse BPUIC boarding-area suffixes and SLOID descendants to the stop.
    return (
        f"regexp_replace(trim({column}), "
        r"'^([0-9]{7})[0-9]{2}$|^(ch:1:sloid:[0-9]+):.*$', '\1\2')"
    )


def _find_pairs(
    db: duckdb.DuckDBPyConnection, hub_stop_ids: dict[str, list[str]], config: dict
) -> None:
    db.execute(f"SET TimeZone = '{TZ}'")
    db.register(
        "hub_ids",
        pd.DataFrame(
            [(hub, key.strip()) for hub, keys in hub_stop_ids.items() for key in keys],
            columns=["hub", "stop_key"],
            dtype="string",
        ).drop_duplicates(),
    )
    data = config["data"]
    lower, upper = config["connections"]["planned_gap_minutes"]
    db.execute(
        f"""
        CREATE TEMP TABLE hub_events AS
        SELECT cast(e.operating_day AS DATE) AS operating_day,
               coalesce(s.hub, n.hub) AS hub, journey_id, product, coalesce(line, '') AS line,
               planned_arrival, actual_arrival, planned_departure, actual_departure, cancelled,
               (NOT cancelled AND ? AND arrival_status = 'REAL' AND actual_arrival IS NOT NULL)
                   AS arr_real,
               (NOT cancelled AND ? AND departure_status = 'REAL' AND actual_departure IS NOT NULL)
                   AS dep_real
        FROM stop_events e
        LEFT JOIN hub_ids s ON s.stop_key = {_stop_key("e.sloid")}
        LEFT JOIN hub_ids n ON n.stop_key = {_stop_key("e.stop_id")}
        WHERE coalesce(s.hub, n.hub) IS NOT NULL
          AND cast(e.operating_day AS DATE) BETWEEN ?::DATE AND ?::DATE
          AND product IN (SELECT unnest(?))
          AND (NOT ? OR NOT additional_trip)
          AND (NOT ? OR NOT pass_through)
          AND (planned_arrival IS NOT NULL OR planned_departure IS NOT NULL)
        """,
        [
            "REAL" in data["keep_status"],
            "REAL" in data["keep_status"],
            data["period"]["start"],
            data["period"]["end"],
            data["scope_products"],
            data["exclude_additional_trips"],
            data["exclude_pass_through"],
        ],
    )
    # Keep the two timestamp inequalities as join keys and the hub/journey check
    # as a residual predicate so DuckDB can select its interval join.
    db.execute("SET prefer_range_joins = true")
    db.execute(
        """
        CREATE TEMP TABLE pairs AS
        SELECT a.hub, a.operating_day, a.journey_id AS arr_journey_id,
               b.journey_id AS dep_journey_id, a.product AS arr_product,
               b.product AS dep_product, a.line AS arr_line, b.line AS dep_line,
               epoch(b.planned_departure - a.planned_arrival) / 60 AS planned_gap_min,
               CASE WHEN a.arr_real AND b.dep_real
                    THEN epoch(b.actual_departure - a.actual_arrival) / 60 END AS actual_gap_min,
               epoch(a.actual_arrival - a.planned_arrival) / 60 AS arr_delay_min,
               CASE WHEN b.dep_real
                    THEN epoch(b.actual_departure - b.planned_departure) / 60 END AS dep_delay_min,
               b.cancelled AS b_cancelled, a.arr_real, b.dep_real,
               hour(a.planned_arrival) * 60 + minute(a.planned_arrival) AS local_minute
        FROM hub_events a
        JOIN hub_events b
          ON b.planned_departure BETWEEN a.planned_arrival + INTERVAL (?)
                                    AND a.planned_arrival + INTERVAL (?)
         AND CASE WHEN a.hub = b.hub THEN a.journey_id <> b.journey_id ELSE false END
        """,
        [f"{lower} minutes", f"{upper} minutes"],
    )
    db.execute("RESET prefer_range_joins")


def _connections_query(db: duckdb.DuckDBPyConnection, config: dict) -> str:
    db.register(
        "bands",
        pd.DataFrame(
            [
                (band, _local_minute(lo), _local_minute(hi))
                for band, (lo, hi) in config["time_bands"].items()
            ],
            columns=["time_band", "lo", "hi"],
        ),
    )
    db.register(
        "halves",
        pd.DataFrame(
            [(half, lo, hi) for half, (lo, hi) in config["data"]["halves"].items()],
            columns=["half", "lo", "hi"],
        ),
    )
    columns = ", ".join(CONNECTIONS)
    return f"""
        SELECT {columns}
        FROM (
            SELECT p.*, bands.time_band, isodow(operating_day) - 1 AS weekday, halves.half
            FROM pairs p
            LEFT JOIN bands ON local_minute >= bands.lo AND local_minute < bands.hi
            LEFT JOIN halves ON operating_day BETWEEN halves.lo::DATE AND halves.hi::DATE
            WHERE arr_real AND (dep_real OR b_cancelled)
        )
        ORDER BY {columns}
    """


def build_connections(
    stop_events: pd.DataFrame, hub_stop_ids: dict[str, list[str]], config: dict
) -> pd.DataFrame:
    """Return CONNECTIONS from STOP_EVENTS, hub identifier lists and study config.

    Gaps and delays are signed elapsed minutes. Cancelled departures have null actual gaps.
    """
    with duckdb.connect() as db:
        db.register("stop_events", stop_events)
        _find_pairs(db, hub_stop_ids, config)
        result = db.sql(_connections_query(db, config)).df(date_as_object=True)
    return result


def _hub_ids(atlas_path: Path, hubs: list[str]) -> dict[str, list[str]]:
    atlas = pd.read_csv(
        atlas_path,
        sep=None,
        engine="python",
        dtype=str,
        keep_default_na=False,
        usecols=["designationOfficial", "isoCountryCode", "number", "sloid"],
    ).apply(lambda column: column.str.strip())
    swiss = atlas.loc[atlas["isoCountryCode"].eq("CH")]
    ids = {}
    for hub in hubs:
        matches = swiss.loc[swiss["designationOfficial"].eq(hub), ["number", "sloid"]]
        numbers = set(matches["number"]) - {""}
        if len(numbers) != 1:
            raise ValueError(f"Expected one Swiss atlas service-point number for {hub!r}")
        ids[hub] = sorted((numbers | set(matches["sloid"])) - {""})
    return ids


def _report(db: duckdb.DuckDBPyConnection, hub_stop_ids: dict[str, list[str]]) -> dict:
    rows = db.execute(
        """
        SELECT hub, operating_day::VARCHAR, count(*) AS candidates,
               count(*) FILTER (WHERE arr_real AND dep_real) AS real_pairs,
               count(*) FILTER (WHERE arr_real AND (dep_real OR b_cancelled)) AS retained_pairs
        FROM pairs
        GROUP BY hub, operating_day
        ORDER BY hub, operating_day
        """
    ).fetchall()
    hubs = {
        hub: {"matched_ids": ids, "pairs": 0, "candidate_pairs": 0, "real_pairs": 0, "by_day": {}}
        for hub, ids in hub_stop_ids.items()
    }
    for hub, day, candidates, real_pairs, retained in rows:
        entry = hubs[hub]
        entry["pairs"] += retained
        entry["candidate_pairs"] += candidates
        entry["real_pairs"] += real_pairs
        entry["by_day"][day] = {"pairs": retained, "candidate_pairs": candidates}
    for entry in hubs.values():
        candidates = entry["candidate_pairs"]
        entry["real_share"] = entry["real_pairs"] / candidates if candidates else None
    return {
        "hubs": hubs,
        "versions": {
            "duckdb": duckdb.__version__,
            "pandas": pd.__version__,
            "pyyaml": yaml.__version__,
        },
    }


def build_connections_file(
    interim_dir: Path, service_points_path: Path, config_path: Path, out_path: Path
) -> Path:
    """Read interim/ist Parquet, atlas CSV and study YAML and return the output Parquet path.

    Gaps and delays are in minutes. Write connections_log.json alongside the Parquet.
    """
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    files = sorted((interim_dir / "ist").glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No STOP_EVENTS Parquet files in {interim_dir / 'ist'}")
    ids = _hub_ids(service_points_path, config["connections"]["hubs"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out_path.parent) as stage, duckdb.connect() as db:
        parquet = Path(stage) / out_path.name
        log = Path(stage) / "connections_log.json"
        db.read_parquet([str(path) for path in files]).create_view("stop_events")
        _find_pairs(db, ids, config)
        db.sql(_connections_query(db, config)).write_parquet(str(parquet))
        log.write_text(json.dumps(_report(db, ids), indent=2) + "\n", encoding="utf-8")
        parquet.replace(out_path)
        log.replace(out_path.parent / log.name)
    return out_path
