"""Table contracts shared by all tickets (INTERFACE — frozen, see tests/test_interfaces.py).

Each schema maps column name -> logical dtype. Producers (UC-011, UC-013, UC-014) must write
exactly these columns; consumers may rely on them before the producer ticket is merged by
using the builders in tests/factories.py.

Logical dtypes: "str", "date", "timestamp" (tz-aware, Europe/Zurich), "float", "int",
"bool". Nullable columns are listed in NULLABLE.
"""

from __future__ import annotations

from collections.abc import Mapping

TZ = "Europe/Zurich"

# data/interim/ist/<YYYY-MM-DD>.parquet — one row per raw Ist-Daten row (UC-011).
STOP_EVENTS: dict[str, str] = {
    "operating_day": "date",
    "journey_id": "str",  # FAHRT_BEZEICHNER
    "operator_id": "str",  # BETREIBER_ID
    "operator_abbr": "str",  # BETREIBER_ABK
    "product": "str",  # PRODUKT_ID
    "line": "str",  # LINIEN_TEXT
    "transport_text": "str",  # VERKEHRSMITTEL_TEXT
    "additional_trip": "bool",  # ZUSATZFAHRT_TF (null -> false)
    "cancelled": "bool",  # FAELLT_AUS_TF (null -> false)
    "stop_id": "str",  # BPUIC (7/9-digit) or SLOID, as published
    "sloid": "str",  # SLOID
    "stop_name": "str",  # HALTESTELLEN_NAME
    "planned_arrival": "timestamp",
    "actual_arrival": "timestamp",
    "arrival_status": "str",  # REAL | ESTIMATED | FORECAST | UNKNOWN (empty -> FORECAST)
    "planned_departure": "timestamp",
    "actual_departure": "timestamp",
    "departure_status": "str",
    "pass_through": "bool",  # DURCHFAHRT_TF (null -> false)
    "source_file": "str",
    "source_row": "int",
}

# data/processed/arrivals.parquet — one row per REAL train arrival at a stop (UC-013).
ARRIVALS: dict[str, str] = {
    "operating_day": "date",
    "journey_id": "str",
    "operator_abbr": "str",
    "product": "str",
    "line": "str",
    "stop_id": "str",
    "stop_name": "str",
    "canton": "str",
    "planned_arrival": "timestamp",
    "actual_arrival": "timestamp",
    "delay_min": "float",  # actual - planned, minutes, negative = early
    "cancelled": "bool",
    "time_band": "str",  # keys of config/study.yaml time_bands
    "weekday": "int",  # 0 = Monday
    "half": "str",  # "first" | "second"
}

# data/processed/connections.parquet — one row per observed A->B pair at a hub (UC-014).
CONNECTIONS: dict[str, str] = {
    "hub": "str",
    "operating_day": "date",
    "arr_journey_id": "str",
    "dep_journey_id": "str",
    "arr_product": "str",
    "dep_product": "str",
    "arr_line": "str",
    "dep_line": "str",
    "planned_gap_min": "float",
    "actual_gap_min": "float",
    "arr_delay_min": "float",
    "dep_delay_min": "float",
    "b_cancelled": "bool",
    "time_band": "str",
    "weekday": "int",
    "half": "str",
}

NULLABLE: dict[str, set[str]] = {
    "STOP_EVENTS": {
        "planned_arrival",
        "actual_arrival",
        "planned_departure",
        "actual_departure",
        "sloid",
        "stop_name",
        "line",
    },
    "ARRIVALS": {"canton", "delay_min", "actual_arrival"},
    "CONNECTIONS": {"actual_gap_min", "dep_delay_min"},
}

TIME_BANDS = ("night", "early", "morning_peak", "midday", "evening_peak", "evening")
HALVES = ("first", "second")
DECISIONS = ("safe", "at_risk", "risky")


def missing_columns(columns: list[str] | tuple[str, ...], schema: Mapping[str, str]) -> list[str]:
    """Return schema columns absent from `columns` (order of the schema)."""
    present = set(columns)
    return [c for c in schema if c not in present]


def extra_columns(columns: list[str] | tuple[str, ...], schema: Mapping[str, str]) -> list[str]:
    """Return columns not defined in `schema`."""
    return [c for c in columns if c not in schema]
