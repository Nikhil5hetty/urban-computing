"""Physical Parquet contract for UC-013."""

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from tests.factories import stop_events
from urban_computing.data.arrivals import build_arrivals_file


def test_arrivals_schema(tmp_path):
    events = stop_events([])
    points = pd.DataFrame(columns=["sloid", "number", "isoCountryCode", "cantonAbbreviation"])
    ist = tmp_path / "ist"
    ist.mkdir()
    events.to_parquet(ist / "sample.parquet", index=False)
    atlas = tmp_path / "atlas.csv"
    points.to_csv(atlas, index=False)
    path = build_arrivals_file(tmp_path, atlas, Path("config/study.yaml"), tmp_path / "out.parquet")
    timestamp = pa.timestamp("us", tz="Europe/Zurich")
    assert pq.read_schema(path).equals(
        pa.schema(
            [
                ("operating_day", pa.date32()),
                ("journey_id", pa.string()),
                ("operator_abbr", pa.string()),
                ("product", pa.string()),
                ("line", pa.string()),
                ("stop_id", pa.string()),
                ("stop_name", pa.string()),
                ("canton", pa.string()),
                ("planned_arrival", timestamp),
                ("actual_arrival", timestamp),
                ("delay_min", pa.float64()),
                ("cancelled", pa.bool_()),
                ("time_band", pa.string()),
                ("weekday", pa.int64()),
                ("half", pa.string()),
            ]
        )
    )
