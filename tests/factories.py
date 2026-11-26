"""Builders for tiny, schema-correct tables and contract objects.

Use these to test a ticket BEFORE its upstream producer ticket is merged (soft
dependencies). They follow urban_computing.data.schemas exactly; tests/test_interfaces.py
checks that.

    from tests.factories import arrivals, connections, stop_events, sample_answer
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from urban_computing.data import schemas

TZ = schemas.TZ
DEFAULT_DAY = date(2026, 10, 5)  # a Monday, first half


def ts(day: date, hhmm: str, seconds: int = 0) -> pd.Timestamp:
    """Local Europe/Zurich timestamp."""
    h, m = map(int, hhmm.split(":"))
    return pd.Timestamp(datetime(day.year, day.month, day.day, h, m, seconds), tz=TZ)


def _coerce(df: pd.DataFrame, schema: dict[str, str]) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for col, kind in schema.items():
        s = df[col]
        if kind == "timestamp":
            t = pd.to_datetime(s)
            out[col] = t.dt.tz_localize(TZ) if t.dt.tz is None else t.dt.tz_convert(TZ)
        elif kind == "float":
            out[col] = s.astype("float64")
        elif kind == "int":
            out[col] = s.astype("int64")
        elif kind == "bool":
            out[col] = s.astype(bool)
        elif kind == "date":
            out[col] = s
        else:
            out[col] = s.astype(object)
    return out


def _half(day: date) -> str:
    return "first" if day.day <= 14 else "second"


def stop_events(rows: Sequence[dict]) -> pd.DataFrame:
    """STOP_EVENTS frame; each row dict overrides defaults (planned/actual times optional)."""
    base = {
        "operating_day": DEFAULT_DAY,
        "journey_id": "J1",
        "operator_id": "85:11",
        "operator_abbr": "SBB",
        "product": "Zug",
        "line": "IC1",
        "transport_text": "IC",
        "additional_trip": False,
        "cancelled": False,
        "stop_id": "8500218",
        "sloid": "ch:1:sloid:218",
        "stop_name": "Olten",
        "planned_arrival": pd.NaT,
        "actual_arrival": pd.NaT,
        "arrival_status": "REAL",
        "planned_departure": pd.NaT,
        "actual_departure": pd.NaT,
        "departure_status": "REAL",
        "pass_through": False,
        "source_file": "synthetic.csv",
        "source_row": 0,
    }
    recs = []
    for i, r in enumerate(rows):
        rec = {**base, "source_row": i, **r}
        recs.append(rec)
    df = pd.DataFrame(recs, columns=list(schemas.STOP_EVENTS))
    return _coerce(df, schemas.STOP_EVENTS)


def arrivals(
    delays: Sequence[float | None], *, start: str = "07:00", every_min: int = 30, **overrides
) -> pd.DataFrame:
    """ARRIVALS frame with one row per delay (None = cancelled). Overrides apply to all rows."""
    day = overrides.pop("operating_day", DEFAULT_DAY)
    first = ts(day, start)
    recs = []
    for i, d in enumerate(delays):
        planned = first + timedelta(minutes=every_min * i)
        cancelled = d is None
        recs.append(
            {
                "operating_day": day,
                "journey_id": f"J{i}",
                "operator_abbr": "SBB",
                "product": "IC",
                "line": "IC1",
                "stop_id": "8500218",
                "stop_name": "Olten",
                "canton": "SO",
                "planned_arrival": planned,
                "actual_arrival": pd.NaT if cancelled else planned + timedelta(minutes=float(d)),
                "delay_min": np.nan if cancelled else float(d),
                "cancelled": cancelled,
                "time_band": "morning_peak",
                "weekday": day.weekday(),
                "half": _half(day),
                **overrides,
            }
        )
    df = pd.DataFrame(recs, columns=list(schemas.ARRIVALS))
    return _coerce(df, schemas.ARRIVALS)


def connections(
    actual_gaps: Sequence[float | None], *, planned_gap_min: float = 4.0, **overrides
) -> pd.DataFrame:
    """CONNECTIONS frame; actual gap None = departing train cancelled."""
    day = overrides.pop("operating_day", DEFAULT_DAY)
    recs = []
    for i, g in enumerate(actual_gaps):
        cancelled = g is None
        gap = np.nan if cancelled else float(g)
        recs.append(
            {
                "hub": "Olten",
                "operating_day": day,
                "arr_journey_id": f"A{i}",
                "dep_journey_id": f"B{i}",
                "arr_product": "IC",
                "dep_product": "IR",
                "arr_line": "IC1",
                "dep_line": "IR16",
                "planned_gap_min": planned_gap_min,
                "actual_gap_min": gap,
                "arr_delay_min": np.nan if cancelled else max(0.0, planned_gap_min - gap),
                "dep_delay_min": np.nan if cancelled else 0.0,
                "b_cancelled": cancelled,
                "time_band": "morning_peak",
                "weekday": day.weekday(),
                "half": _half(day),
                **overrides,
            }
        )
    df = pd.DataFrame(recs, columns=list(schemas.CONNECTIONS))
    return _coerce(df, schemas.CONNECTIONS)


def sample_question(**overrides):
    from urban_computing.assistant.contract import Question

    base = {
        "hub": "Olten",
        "arr_line": "IC1",
        "dep_line": "IR16",
        "time_band": "morning_peak",
        "weekday_group": "monday",
        "margin_min": 4.0,
        "question_id": "q-test-1",
    }
    return Question(**{**base, **overrides})


def sample_answer(decision: str = "at_risk", **overrides):
    """A plausible Answer for UI / LLM / evaluation tests (numbers are made up)."""
    from urban_computing.assistant.contract import Answer, Explanation, Provenance

    base = {
        "question": sample_question(),
        "decision": decision,
        "p_miss": 0.18,
        "explanations": [
            Explanation(
                sentence="Few of your connections at Olten are missed.",
                quantifier="few",
                summarizer="connection_slack_minutes:missed",
                restriction="hub=Olten&weekday_group=monday",
                truth=0.74,
                coverage=0.9,
                quality=0.67,
                n=38,
            )
        ],
        "crisp_decision": "safe",
        "crisp_sentences": ["Most IC1 arrivals at Olten are punctual."],
        "provenance": Provenance(period="2026-10-01..2026-10-28", config_hash="test"),
    }
    return Answer(**{**base, **overrides})


def assert_schema(df: pd.DataFrame, schema: dict[str, str]) -> None:
    """Assert exact column set/order and dtype families of a frame."""
    assert list(df.columns) == list(schema), (list(df.columns), list(schema))
    for col, kind in schema.items():
        dt = df[col].dtype
        if kind == "timestamp":
            assert isinstance(dt, pd.DatetimeTZDtype), (col, dt)
        elif kind == "float":
            assert pd.api.types.is_float_dtype(dt), (col, dt)
        elif kind == "int":
            assert pd.api.types.is_integer_dtype(dt), (col, dt)
        elif kind == "bool":
            assert pd.api.types.is_bool_dtype(dt), (col, dt)
