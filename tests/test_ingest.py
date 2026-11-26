from __future__ import annotations

import csv
import difflib
import json
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq
import pytest
import yaml

from tests.factories import assert_schema, stop_events, ts
from urban_computing.data.ingest import _csv_header, _detect_encoding, ingest_all, ingest_day
from urban_computing.data.schemas import STOP_EVENTS

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "ist_sample"


def test_fixture_ingest_is_lossless_and_deterministic(tmp_path):
    out = tmp_path / "ist"
    reports = ingest_all(FIXTURE, out)
    assert len(reports) == 3
    first_run = {}
    for report in reports:
        source = FIXTURE / report.source_file
        with source.open(encoding="utf-8", newline="") as stream:
            raw = list(csv.DictReader(stream, delimiter=";"))
        day = date.fromisoformat(source.name[:10])
        parquet = out / f"{day}.parquet"
        first_run[parquet] = parquet.read_bytes()
        frame = pq.read_table(parquet).to_pandas()
        assert_schema(frame, STOP_EVENTS)
        assert report.rows_in == report.rows_out == len(raw) == len(frame)
        assert frame["operating_day"].tolist() == [day] * len(raw)
        assert frame["journey_id"].tolist() == [row["FAHRT_BEZEICHNER"] for row in raw]
        assert frame["source_row"].tolist() == list(range(len(raw)))
        assert frame["source_file"].tolist() == [source.name] * len(raw)
        assert not any(report.parse_failures.values())

    first_day = pq.read_table(out / "2026-10-01.parquet").to_pandas()
    expected = stop_events([{"planned_arrival": ts(date(2026, 10, 1), "06:00")}])
    assert first_day.loc[0, "planned_arrival"] == expected.loc[0, "planned_arrival"]
    assert str(first_day["planned_arrival"].dtype.tz) == "Europe/Zurich"
    assert not first_day.loc[0, ["additional_trip", "cancelled", "pass_through"]].any()
    assert first_day.loc[0, "departure_status"] == "FORECAST"
    report_file = tmp_path / "ingest_report.json"
    first_run[report_file] = report_file.read_bytes()
    assert ingest_all(FIXTURE, out) == reports
    assert all(path.read_bytes() == content for path, content in first_run.items())


def test_reordered_legacy_encoding_and_mixed_case_daily_discovery(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    fixture_day = FIXTURE / "2026-10-01_IstDaten.csv"
    with fixture_day.open(encoding="utf-8", newline="") as stream:
        sample = csv.DictReader(stream, delimiter=";")
        header = [name for name in reversed(sample.fieldnames) if name != "_id"]
        row = next(sample)

    path = raw / "2026-10-12_istdaten.CSV"
    with path.open("w", encoding="cp1252", newline="") as stream:
        writer = csv.DictWriter(stream, header, extrasaction="ignore")
        writer.writeheader()
        for stop in ("0123456", "001234567", "ch:1:sloid:218"):
            writer.writerow(
                row
                | {
                    "BETRIEBSTAG": "12.10.2026",
                    "BPUIC": stop,
                    "ANKUNFTSZEIT": "not a timestamp",
                    "AN_PROGNOSE": "12.10.2026 6:01:02",
                    "FAELLT_AUS_TF": "true",
                }
            )
    (raw / "ist-daten-v2.zip").write_bytes(b"ignored")
    out = tmp_path / "ist"
    (report,) = ingest_all(raw, out)

    frame = pq.read_table(out / "2026-10-12.parquet").to_pandas()
    assert frame["stop_id"].tolist() == ["0123456", "001234567", "ch:1:sloid:218"]
    assert frame["sloid"].tolist() == [row["SLOID"]] * 3
    assert frame["stop_name"].tolist() == ["Zürich HB"] * 3
    assert frame["actual_arrival"].tolist() == [ts(date(2026, 10, 12), "06:01", 2)] * 3
    assert frame["planned_arrival"].isna().all()
    assert frame["cancelled"].all()
    assert report.rows_in == report.rows_out == 3
    assert report.parse_failures["planned_arrival"] == 3
    assert report.parse_failures["planned_departure"] == 0
    assert report.status_values == {"arrival_status:REAL": 3, "departure_status:FORECAST": 3}
    payload = json.loads((tmp_path / "ingest_report.json").read_text(encoding="utf-8"))
    assert set(payload["versions"]) == {"duckdb", "pyarrow"}
    (saved,) = payload["files"]
    assert saved["source_file"] == path.name
    assert (saved["separator"], saved["encoding"]) == (",", "cp1252")


def test_rows_and_provenance_across_arrow_batches(tmp_path):
    fixture = FIXTURE / "2026-10-01_IstDaten.csv"
    with fixture.open(encoding="utf-8") as stream:
        header, row = stream.readline(), stream.readline()
    source = tmp_path / fixture.name
    with source.open("w", encoding="utf-8") as stream:
        stream.write(header)
        for _ in range(65_537):
            stream.write(row)

    report = ingest_day(source, tmp_path / "ist")
    parquet = pq.ParquetFile(tmp_path / "ist" / "2026-10-01.parquet")
    assert report.rows_in == report.rows_out == parquet.metadata.num_rows == 65_537
    assert parquet.num_row_groups == 2
    assert parquet.read_row_group(1, columns=["source_row"])["source_row"].to_pylist() == [65_536]


def test_missing_required_column_does_not_publish(tmp_path):
    csv_path = tmp_path / "2026-10-01.csv"
    csv_path.write_text("BETRIEBSTAG;FAHRT_BEZEICHNER\n1.10.2026;J1\n", encoding="utf-8")
    out = tmp_path / "ist"
    with pytest.raises(ValueError, match="missing CSV columns: .*BPUIC"):
        ingest_day(csv_path, out)
    assert not list(out.iterdir())


@pytest.mark.realdata
def test_first_real_day_header_and_ingest(tmp_path):
    config = yaml.safe_load((ROOT / "config" / "study.yaml").read_text(encoding="utf-8"))
    directory = ROOT / config["data"]["raw_dir"]
    paths = sorted(
        path for path in directory.glob("*") if path.is_file() and path.suffix.lower() == ".csv"
    )
    if not paths:
        pytest.skip(f"No real CSVs under {directory}")
    source = paths[0]
    fixture = FIXTURE / "2026-10-01_IstDaten.csv"
    _, fixture_header = _csv_header(fixture, _detect_encoding(fixture))
    encoding = _detect_encoding(source)
    separator, real_header = _csv_header(source, encoding)
    diff = "\n".join(
        difflib.unified_diff(
            fixture_header, real_header, fromfile=fixture.name, tofile=source.name, lineterm=""
        )
    )
    print(
        f"{source.name}, separator={separator!r}, encoding={encoding}:\n{diff or 'Headers match'}"
    )
    with source.open(encoding=encoding, newline="") as stream:
        records = csv.reader(stream, delimiter=separator, strict=True)
        next(records)
        expected_rows = sum(bool(row) for row in records)
    report = ingest_day(source, tmp_path)
    assert report.rows_in == report.rows_out == expected_rows > 0
    (parquet,) = tmp_path.glob("*.parquet")
    assert pq.read_schema(parquet).names == list(STOP_EVENTS)
    print(f"{report.rows_out:,} rows; parse failures: {report.parse_failures}")
