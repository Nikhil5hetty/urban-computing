"""Build the arrivals fact table from STOP_EVENTS and atlas service points."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from urban_computing.data.schemas import ARRIVALS, TZ

# D-024 covers both folds of the repeated local hour.
_DST_START = pd.Timestamp("2026-10-25 00:00:00Z")
_DST_END = pd.Timestamp("2026-10-25 02:00:00Z")
_TYPES = {
    "date": pa.date32(),
    "str": pa.string(),
    "timestamp": pa.timestamp("us", tz=TZ),
    "float": pa.float64(),
    "bool": pa.bool_(),
    "int": pa.int64(),
}
_SCHEMA = pa.schema([(name, _TYPES[kind]) for name, kind in ARRIVALS.items()])
_ATLAS_COLUMNS = ["sloid", "number", "isoCountryCode", "cantonAbbreviation"]


def _atlas_lookup(service_points: pd.DataFrame) -> pd.DataFrame:
    # Atlas documents number as the stop-level DiDok code and isoCountryCode
    # as geographic (unlike the issuing country encoded in the DiDok number).
    points = service_points[_ATLAS_COLUMNS].astype("string").apply(lambda s: s.str.strip())
    points = points.replace("", pd.NA)
    keys = (
        points.melt(id_vars=["isoCountryCode", "cantonAbbreviation"], value_name="stop_key")
        .drop(columns="variable")
        .dropna(subset="stop_key")
        .drop_duplicates()
    )
    lookup = keys.set_index("stop_key")
    if not lookup.index.is_unique:
        raise ValueError("Atlas service points contain conflicting records for a stop identifier")
    return lookup


def _stop_key(ids: pd.Series) -> pd.Series:
    return (
        ids.astype("string")
        .str.strip()
        .str.replace(r"^([0-9]{7})[0-9]{2}$|^(ch:1:sloid:[0-9]+):.*$", r"\1\2", regex=True)
    )


def _minutes(hhmm: str) -> int:
    hour, minute = map(int, hhmm.split(":"))
    return hour * 60 + minute


def _build(
    events: pd.DataFrame, atlas: pd.DataFrame, config: dict, counts: Counter
) -> pd.DataFrame:
    data = config["data"]
    days = pd.to_datetime(events["operating_day"])
    cancelled = events["cancelled"]
    actual = events["actual_arrival"].dt.tz_convert(TZ)
    planned = events["planned_arrival"].dt.tz_convert(TZ)
    measured = (
        events["arrival_status"].eq("REAL")
        & events["arrival_status"].isin(data["keep_status"])
        & actual.notna()
    )
    in_dst = planned.between(_DST_START, _DST_END, inclusive="left") | actual.between(
        _DST_START, _DST_END, inclusive="left"
    )

    keep = pd.Series(True, index=events.index)
    for stage, mask in (
        (
            "period",
            days.between(
                pd.Timestamp(data["period"]["start"]), pd.Timestamp(data["period"]["end"])
            ),
        ),
        ("scope_products", events["product"].isin(data["scope_products"])),
        (
            "exclude_additional_trips",
            ~events["additional_trip"] | (not data["exclude_additional_trips"]),
        ),
        ("exclude_pass_through", ~events["pass_through"] | (not data["exclude_pass_through"])),
        ("has_arrival", planned.notna()),
        ("real_or_cancelled", measured | cancelled),
    ):
        counts[stage + "_in"] += int(keep.sum())
        keep &= mask
        counts[stage + "_out"] += int(keep.sum())

    counts["i5_measurable_before_geographic_filter"] += int(
        (keep & measured & ~cancelled & ~in_dst).sum()
    )
    candidates = events.loc[keep]
    bpuic = _stop_key(candidates["stop_id"])
    sloid = _stop_key(candidates["sloid"])
    key = sloid.where(sloid.isin(atlas.index), bpuic)
    country = key.map(atlas["isoCountryCode"]).astype("string")
    # Use the issuing country only as a fallback for unmapped numeric IDs.
    foreign_code = bpuic.str.fullmatch(r"[0-9]{7}", na=False) & ~bpuic.str.startswith(
        "85", na=False
    )
    foreign = country.ne("CH").fillna(foreign_code)
    counts["foreign_rows_excluded"] += int(foreign.sum())
    result = candidates.loc[~foreign, list(events.columns.intersection(ARRIVALS))].copy()
    idx = result.index
    counts["unmatched_rows"] += int((~key.loc[idx].isin(atlas.index)).sum())
    counts["ambiguous_dst_rows"] += int(in_dst.loc[idx].sum())
    counts["rows_out"] += len(result)

    result["canton"] = key.loc[idx].map(atlas["cantonAbbreviation"])
    result["planned_arrival"] = planned.loc[idx]
    result["actual_arrival"] = actual.loc[idx].mask(cancelled.loc[idx])
    result["delay_min"] = ((actual.loc[idx] - planned.loc[idx]).dt.total_seconds() / 60).mask(
        cancelled.loc[idx] | in_dst.loc[idx]
    )
    local_minute = planned.loc[idx].dt.hour * 60 + planned.loc[idx].dt.minute
    result["time_band"] = pd.Series(pd.NA, index=idx, dtype="string")
    for band, (start, end) in config["time_bands"].items():
        result.loc[
            local_minute.between(_minutes(start), _minutes(end), inclusive="left"), "time_band"
        ] = band
    result["weekday"] = days.loc[idx].dt.day_of_week.astype("int64")
    result["half"] = pd.Series(pd.NA, index=idx, dtype="string")
    for half, (start_day, end_day) in data["halves"].items():
        result.loc[
            days.loc[idx].between(pd.Timestamp(start_day), pd.Timestamp(end_day)), "half"
        ] = half
    if result[["time_band", "half"]].isna().any().any():
        raise ValueError("Study time bands and halves must cover the retained arrivals")
    # STOP_EVENTS permits absent source labels. ARRIVALS requires strings.
    for column in ("stop_name", "line"):
        result[column] = result[column].fillna("")
    return result[list(ARRIVALS)].reset_index(drop=True)


def build_arrivals(
    stop_events: pd.DataFrame, service_points: pd.DataFrame, config: dict
) -> pd.DataFrame:
    """Return ARRIVALS from STOP_EVENTS, atlas v2 columns, and study config.

    Arrival timestamps use Europe/Zurich and signed elapsed delays are in minutes.
    """
    return _build(
        stop_events.reset_index(drop=True), _atlas_lookup(service_points), config, Counter()
    )


def build_arrivals_file(
    interim_dir: Path, service_points_path: Path, config_path: Path, out_path: Path
) -> Path:
    """Stream interim/ist Parquet to ARRIVALS and log row counts beside the output.

    Read the atlas v2 CSV and study YAML. Return the written Parquet path.
    """
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    atlas = _atlas_lookup(
        pd.read_csv(
            service_points_path,
            sep=None,
            engine="python",
            dtype=str,
            usecols=_ATLAS_COLUMNS,
            keep_default_na=False,
        )
    )
    files = sorted((interim_dir / "ist").glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No STOP_EVENTS Parquet files in {interim_dir / 'ist'}")

    counts: Counter = Counter()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out_path.parent) as staging:
        staged_parquet = Path(staging) / out_path.name
        staged_log = Path(staging) / "arrivals_log.json"
        with duckdb.connect() as connection, pq.ParquetWriter(staged_parquet, _SCHEMA) as writer:
            connection.execute(f"SET TimeZone = '{TZ}'")
            for path in files:
                for batch in connection.read_parquet(str(path)).to_arrow_reader(100_000):
                    frame = _build(batch.to_pandas(), atlas, config, counts)
                    writer.write_table(
                        pa.Table.from_pandas(frame, schema=_SCHEMA, preserve_index=False)
                    )
        total = counts["rows_out"]
        report = {
            "rows_in": counts["period_in"],
            "rows_out": total,
            "filters": [
                {"filter": stage, "before": counts[stage + "_in"], "after": counts[stage + "_out"]}
                for stage in (
                    "period",
                    "scope_products",
                    "exclude_additional_trips",
                    "exclude_pass_through",
                    "has_arrival",
                    "real_or_cancelled",
                )
            ],
            "foreign_rows_excluded": counts["foreign_rows_excluded"],
            "ambiguous_dst_rows": counts["ambiguous_dst_rows"],
            "unmatched_rows": counts["unmatched_rows"],
            "unmatched_share": counts["unmatched_rows"] / total if total else None,
            "i5_measurable_before_geographic_filter": counts[
                "i5_measurable_before_geographic_filter"
            ],
            "versions": {
                "duckdb": duckdb.__version__,
                "pandas": pd.__version__,
                "pyarrow": pa.__version__,
                "pyyaml": yaml.__version__,
            },
        }
        staged_log.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        staged_parquet.replace(out_path)
        staged_log.replace(out_path.parent / staged_log.name)
    return out_path
