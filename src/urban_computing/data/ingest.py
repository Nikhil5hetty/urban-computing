"""Stream daily Ist-Daten CSVs into the STOP_EVENTS Parquet schema."""

from __future__ import annotations

import codecs
import csv
import json
import re
import shutil
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from urban_computing.data.schemas import STOP_EVENTS, TZ

_RAW_COLUMNS = {
    "operating_day": "BETRIEBSTAG",
    "journey_id": "FAHRT_BEZEICHNER",
    "operator_id": "BETREIBER_ID",
    "operator_abbr": "BETREIBER_ABK",
    "product": "PRODUKT_ID",
    "line": "LINIEN_TEXT",
    "transport_text": "VERKEHRSMITTEL_TEXT",
    "additional_trip": "ZUSATZFAHRT_TF",
    "cancelled": "FAELLT_AUS_TF",
    "stop_id": "BPUIC",
    "sloid": "SLOID",
    "stop_name": "HALTESTELLEN_NAME",
    "planned_arrival": "ANKUNFTSZEIT",
    "actual_arrival": "AN_PROGNOSE",
    "arrival_status": "AN_PROGNOSE_STATUS",
    "planned_departure": "ABFAHRTSZEIT",
    "actual_departure": "AB_PROGNOSE",
    "departure_status": "AB_PROGNOSE_STATUS",
    "pass_through": "DURCHFAHRT_TF",
}
_ARROW_TYPES = {
    "str": pa.string(),
    "date": pa.date32(),
    "timestamp": pa.timestamp("us", tz=TZ),
    "bool": pa.bool_(),
    "int": pa.int64(),
}
_SCHEMA = pa.schema([(name, _ARROW_TYPES[kind]) for name, kind in STOP_EVENTS.items()])
_STATUS_COLUMNS = ("arrival_status", "departure_status")


@dataclass
class IngestReport:
    source_file: str
    rows_in: int
    rows_out: int
    separator: str
    encoding: str
    parse_failures: dict[str, int] = field(default_factory=dict)
    status_values: dict[str, int] = field(default_factory=dict)


def _detect_encoding(path: Path) -> str:
    with path.open("rb") as stream:
        prefix = stream.read(4)
    for bom, encoding in (
        (codecs.BOM_UTF8, "utf-8-sig"),
        (codecs.BOM_UTF16_LE, "utf-16"),
        (codecs.BOM_UTF16_BE, "utf-16"),
    ):
        if prefix.startswith(bom):
            return encoding

    for encoding in ("utf-8", "cp1252"):
        try:
            with path.open(encoding=encoding, newline="") as stream:
                while stream.read(1024 * 1024):
                    pass
        except UnicodeDecodeError:
            continue
        return encoding
    return "latin-1"


def _csv_header(path: Path, encoding: str) -> tuple[str, list[str]]:
    with path.open(encoding=encoding, newline="") as stream:
        line = stream.readline()
    try:
        separator = csv.Sniffer().sniff(line, delimiters=",;\t|").delimiter
    except csv.Error as error:
        raise ValueError(f"{path}: could not detect the CSV separator") from error
    return separator, next(csv.reader([line], delimiter=separator))


def _projection(header: list[str], path: Path) -> tuple[list[str], dict[str, str]]:
    names = {name.strip().upper(): name for name in header}
    if len(names) != len(header):
        raise ValueError(f"{path}: duplicate CSV column names")
    missing = set(_RAW_COLUMNS.values()) - names.keys() - {"SLOID"}
    if missing:
        raise ValueError(f"{path}: missing CSV columns: {', '.join(sorted(missing))}")

    columns = []
    failures = {}
    for name, raw in _RAW_COLUMNS.items():
        if raw not in names:
            columns.append(f"NULL::VARCHAR AS {name}")
            continue
        identifier = '"' + names[raw].replace('"', '""') + '"'
        value = f"nullif(trim({identifier}), '')"
        kind = STOP_EVENTS[name]
        if kind == "date":
            parsed = f"try_strptime({value}, '%d.%m.%Y')::DATE"
        elif kind == "timestamp":
            parsed = (
                f"timezone('{TZ}', try_strptime({value}, ['%d.%m.%Y %H:%M:%S', '%d.%m.%Y %H:%M']))"
            )
        elif kind == "bool":
            parsed = f"try_cast({value} AS BOOLEAN)"
        else:
            expression = f"coalesce({value}, 'FORECAST')" if name in _STATUS_COLUMNS else identifier
            columns.append(f"{expression} AS {name}")
            continue

        failures[name] = f"({value} IS NOT NULL AND {parsed} IS NULL) AS failed_{name}"
        expression = f"coalesce({parsed}, false)" if kind == "bool" else parsed
        columns.append(f"{expression} AS {name}")
    return columns, failures


def _write_day(csv_path: Path, directory: Path) -> tuple[Path, IngestReport]:
    encoding = _detect_encoding(csv_path)
    separator, header = _csv_header(csv_path, encoding)
    columns, failure_flags = _projection(header, csv_path)
    report = IngestReport(csv_path.name, 0, 0, separator, encoding, dict.fromkeys(failure_flags, 0))
    statuses: Counter[str] = Counter()
    filename_date = re.match(r"\d{4}-\d{2}-\d{2}(?!\d)", csv_path.name)
    day = date.fromisoformat(filename_date[0]) if filename_date else None
    output = directory / "day.parquet"
    source = csv_path
    if encoding not in {"utf-8", "utf-8-sig"}:
        source = directory / "decoded.csv"
        with csv_path.open(encoding=encoding, newline="") as original:
            with source.open("w", encoding="utf-8", newline="") as decoded:
                shutil.copyfileobj(original, decoded, length=1024 * 1024)

    projections = ", ".join(columns)
    flags = ", ".join(failure_flags.values())
    with duckdb.connect(config={"memory_limit": "256MB", "threads": 1}) as connection:
        connection.execute(f"SET TimeZone = '{TZ}'")
        connection.read_csv(
            str(source),
            header=True,
            delimiter=separator,
            names=header,
            all_varchar=True,
            parallel=False,
        ).create_view("raw")
        reader = connection.sql(
            f"SELECT {projections}, ? AS source_file, row_number() OVER () - 1 AS source_row, "
            f"{flags} FROM raw",
            params=[csv_path.name],
        ).to_arrow_reader(65_536)
        with reader, pq.ParquetWriter(output, _SCHEMA) as writer:
            for batch in reader:
                report.rows_in += batch.num_rows
                bounds = pc.min_max(batch.column("operating_day")).as_py()
                if bounds["min"] is not None:
                    day = day or bounds["min"]
                    if day != bounds["min"] or day != bounds["max"]:
                        raise ValueError(f"{csv_path}: operating days disagree with {day}")
                for name in failure_flags:
                    report.parse_failures[name] += pc.sum(batch.column(f"failed_{name}")).as_py()
                for name in _STATUS_COLUMNS:
                    for value in pc.value_counts(batch.column(name)).to_pylist():
                        statuses[f"{name}:{value['values']}"] += value["counts"]
                writer.write_batch(batch.select(_SCHEMA.names).cast(_SCHEMA))

    if day is None:
        raise ValueError(f"{csv_path}: cannot determine the operating day")
    report.rows_out = pq.read_metadata(output).num_rows
    if report.rows_out != report.rows_in:
        raise ValueError(f"{csv_path}: row count changed during ingestion")
    report.status_values = dict(sorted(statuses.items()))
    destination = directory / f"{day.isoformat()}.parquet"
    output.replace(destination)
    return destination, report


def ingest_day(csv_path: Path, out_dir: Path) -> IngestReport:
    """Read a daily CSV and write a dated STOP_EVENTS Parquet in out_dir.

    Timestamps are Europe/Zurich instants. Report counts are CSV records and Parquet rows.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out_dir) as staging:
        output, report = _write_day(csv_path, Path(staging))
        output.replace(out_dir / output.name)
    return report


def ingest_all(raw_dir: Path, out_dir: Path) -> list[IngestReport]:
    """Ingest daily CSVs into out_dir and write a JSON report in its parent.

    Return per-file reports in filename order. Non-CSV entries are ignored.
    """
    paths = sorted(
        path for path in raw_dir.iterdir() if path.is_file() and path.suffix.lower() == ".csv"
    )
    if not paths:
        raise ValueError(f"{raw_dir}: no daily CSVs found")
    out_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    with TemporaryDirectory(dir=out_dir) as staging:
        stage = Path(staging)
        outputs = set()
        for path in paths:
            with TemporaryDirectory(dir=stage) as daily:
                output, report = _write_day(path, Path(daily))
                if output.name in outputs:
                    raise ValueError(f"{path}: multiple CSVs for {output.stem}")
                outputs.add(output.name)
                output.replace(stage / output.name)
                reports.append(report)
        report_file = stage / "ingest_report.json"
        payload = {
            "versions": {"duckdb": duckdb.__version__, "pyarrow": pa.__version__},
            "files": [asdict(report) for report in reports],
        }
        report_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        for name in sorted(outputs):
            (stage / name).replace(out_dir / name)
        report_file.replace(out_dir.parent / report_file.name)
    return reports
