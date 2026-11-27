"""Data-quality report and invariant I5 (UC-012)."""

from __future__ import annotations

import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import pyarrow
import yaml

from urban_computing.data.ingest import _csv_header, _detect_encoding
from urban_computing.data.schemas import TZ

# Both folds of 02:00–02:59 Europe/Zurich on 2026-10-25.
_DST_START = "TIMESTAMPTZ '2026-10-25 00:00:00+00'"
_DST_END = "TIMESTAMPTZ '2026-10-25 02:00:00+00'"
# Band specified in eval/hypotheses.yaml (I5).
_I5_BAND = (0.80, 0.99)
_STATUSES = ("REAL", "ESTIMATED", "FORECAST", "UNKNOWN", "")


def _in_dst_hour(column: str) -> str:
    return f"({column} >= {_DST_START} AND {column} < {_DST_END})"


def _open_events(connection: duckdb.DuckDBPyConnection, interim_dir: Path) -> None:
    files = sorted((interim_dir / "ist").glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No STOP_EVENTS Parquet files in {interim_dir / 'ist'}")
    connection.read_parquet([str(path) for path in files]).create_view("events")


def _period(config: dict) -> tuple:
    period = config["data"]["period"]
    return period["start"], period["end"]


_ARRIVAL_DST = " OR ".join(_in_dst_hour(f"{kind}_arrival") for kind in ("planned", "actual"))
_EVENT_DST = " OR ".join(
    [
        _ARRIVAL_DST,
        *(_in_dst_hour(f"{kind}_departure") for kind in ("planned", "actual")),
    ]
)

_SCOPED = """
    WITH scoped AS (
        SELECT *,
            product IN ? AS train,
            NOT (? AND additional_trip) AS regular,
            NOT (? AND pass_through) AS stopping,
            planned_arrival IS NOT NULL AS has_arrival,
            epoch(actual_arrival - planned_arrival) AS delay_seconds
        FROM events
        WHERE operating_day BETWEEN ?::DATE AND ?::DATE
    )
"""

_ELIGIBLE = f""", eligible AS (
        SELECT *, train AND regular AND stopping AND has_arrival AND arrival_status IN ? AS kept,
            arrival_status = 'REAL' AND NOT cancelled
                AND delay_seconds IS NOT NULL AND NOT ({_ARRIVAL_DST}) AS measured
        FROM scoped
    )
"""


def _i5(n: int, punctual: int) -> dict:
    value = punctual / n if n else None
    low, high = _I5_BAND
    return {
        "value": value,
        "pass": value is not None and low <= value <= high,
        "arrivals": n,
        "punctual": punctual,
    }


def _scope_params(config: dict) -> list:
    data = config["data"]
    return [
        data["scope_products"],
        data["exclude_additional_trips"],
        data["exclude_pass_through"],
        *_period(config),
    ]


def _punctuality(connection: duckdb.DuckDBPyConnection, config: dict) -> tuple[dict, list[dict]]:
    counts = connection.execute(
        _SCOPED
        + _ELIGIBLE
        + """
        SELECT (SELECT count(*) FROM events), count(*), count_if(train),
            count_if(train AND regular), count_if(train AND regular AND stopping),
            count_if(train AND regular AND stopping AND has_arrival),
            count_if(kept), count_if(kept AND measured),
            count_if(kept AND measured AND delay_seconds < ?)
        FROM eligible
        """,
        [
            *_scope_params(config),
            config["data"]["keep_status"],
            config["crisp_baseline"]["punctual_threshold_minutes"] * 60,
        ],
    ).fetchone()
    *counts, punctual = (value or 0 for value in counts)
    names = (
        "period",
        "scope_products",
        "exclude_additional_trips",
        "exclude_pass_through",
        "has_arrival",
        "keep_status",
        "measurable_real_arrival",
    )
    filters = [
        {"filter": name, "before": before, "after": after}
        for name, before, after in zip(names, counts[:-1], counts[1:], strict=True)
    ]
    return _i5(counts[-1], punctual), filters


def _blank_statuses(
    connection: duckdb.DuckDBPyConnection, config: dict, sources: list[str], interim_dir: Path
) -> Counter | None:
    raw = Path(config["data"]["raw_dir"])
    paths = [raw / source for source in sources]
    if not paths or not all(path.is_file() for path in paths):
        return None
    metadata = interim_dir / "ingest_report.json"
    encodings = {}
    if metadata.is_file():
        ingested = json.loads(metadata.read_text(encoding="utf-8"))
        encodings = {record["source_file"]: record["encoding"] for record in ingested["files"]}
    blanks = Counter()
    start, end = _period(config)
    for path in paths:
        encoding = encodings.get(path.name) or _detect_encoding(path)
        delimiter, header = _csv_header(path, encoding)
        names = {name.strip().upper(): '"' + name.replace('"', '""') + '"' for name in header}
        operator = names["BETREIBER_ABK"]
        product = names["PRODUKT_ID"]
        status = names["AN_PROGNOSE_STATUS"]
        day = names["BETRIEBSTAG"]
        arrival = names["ANKUNFTSZEIT"]
        with TemporaryDirectory() as staging:
            source = path
            if encoding not in {"utf-8", "utf-8-sig"}:
                source = Path(staging) / "decoded.csv"
                with path.open(encoding=encoding, newline="") as original:
                    with source.open("w", encoding="utf-8", newline="") as decoded:
                        shutil.copyfileobj(original, decoded, length=1024 * 1024)
            connection.read_csv(
                str(source),
                header=True,
                delimiter=delimiter,
                names=header,
                all_varchar=True,
                force_not_null=header,
            ).create_view("raw_statuses", replace=True)
            rows = connection.execute(
                f"""
                SELECT coalesce({operator}, ''), coalesce({product}, ''), count(*)
                FROM raw_statuses
                WHERE trim({status}) = ''
                    AND try_strptime(trim({arrival}),
                        ['%d.%m.%Y %H:%M:%S', '%d.%m.%Y %H:%M']) IS NOT NULL
                    AND try_strptime(trim({day}), '%d.%m.%Y')::DATE BETWEEN ?::DATE AND ?::DATE
                GROUP BY 1, 2
                """,
                [start, end],
            ).fetchall()
            for op, prod, count in rows:
                blanks[op, prod] += count
    return blanks


def _diagnostics(connection: duckdb.DuckDBPyConnection, config: dict, interim_dir: Path) -> dict:
    rows = connection.execute(
        _SCOPED
        + f"""
        SELECT coalesce(operator_abbr, ''), coalesce(product, ''), coalesce(transport_text, ''),
            coalesce(trim(arrival_status), ''),
            count(*), count_if(has_arrival),
            count_if(has_arrival AND train AND regular AND stopping),
            count_if(actual_departure < actual_arrival),
            count_if(actual_departure < planned_departure),
            count_if(abs(epoch(actual_arrival - planned_arrival)) > 21600),
            count_if(stop_name IS NULL OR trim(stop_name) = ''),
            count_if(cancelled), count_if(pass_through), count_if({_EVENT_DST}),
            list(DISTINCT source_file ORDER BY source_file)
        FROM scoped
        GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 4
        """,
        _scope_params(config),
    ).fetchall()
    products = Counter()
    statuses = defaultdict(Counter)
    operators = defaultdict(Counter)
    no_arrival = 0
    dst = Counter()
    anomalies = dict.fromkeys(
        (
            "departure_before_arrival",
            "departure_before_planned",
            "arrival_over_6_hours",
            "empty_stop_name",
            "cancelled",
            "pass_through",
        ),
        0,
    )
    sources = set()
    for row in rows:
        (
            operator,
            product,
            transport,
            status,
            count,
            arrivals,
            scoped,
            *metrics,
            ambiguous,
            files,
        ) = row
        products[product, transport] += count
        no_arrival += count - (arrivals or 0)
        if arrivals:
            statuses[operator, product][status] += arrivals
        if scoped:
            operators[operator][status] += scoped
        dst[operator] += ambiguous or 0
        sources.update(files)
        for name, value in zip(anomalies, metrics, strict=True):
            anomalies[name] += value or 0

    blanks = _blank_statuses(connection, config, sorted(sources), interim_dir)
    if blanks is not None:
        for key, count in blanks.items():
            group = statuses[key]
            # UC-011 normalizes blank CSV values to FORECAST.
            if count < group[""] or count - group[""] > group["FORECAST"]:
                raise ValueError(f"CSV and Parquet blank arrival statuses disagree for {key!r}")
            group["FORECAST"] -= count - group[""]
            group[""] = count

    coverage = []
    for (operator, product), counts in sorted(statuses.items()):
        total = counts.total()
        for status in sorted(set(_STATUSES) | counts.keys()):
            coverage.append(
                {
                    "operator": operator,
                    "product": product,
                    "status": status,
                    "rows": counts[status],
                    "share": counts[status] / total,
                }
            )
    return {
        "products": [
            {"product": product, "transport_text": transport, "rows": count}
            for (product, transport), count in sorted(products.items())
        ],
        "status_basis": "raw_blanks_recovered" if blanks is not None else "parquet_normalized",
        "arrival_status": coverage,
        "rows_without_planned_arrival": no_arrival,
        "low_real_coverage": [
            {
                "operator": operator,
                "rows": counts.total(),
                "real_share": counts["REAL"] / counts.total(),
            }
            for operator, counts in sorted(operators.items())
            if 2 * counts["REAL"] < counts.total()
        ],
        "anomalies": anomalies,
        "ambiguous_dst": [
            {"operator": operator, "rows": count} for operator, count in sorted(dst.items())
        ],
    }


def _markdown(report: dict) -> str:
    i5 = report["I5"]
    share = "undefined" if i5["value"] is None else f"{i5['value']:.2%}"
    verdict = "PASS" if i5["pass"] else "FAIL"
    period = report["period"]
    lines = [
        "# Data-quality report",
        "",
        f"**I5 {verdict}** · {share} ({i5['punctual']:,} of {i5['arrivals']:,} arrivals)",
        "",
        f"Operating days {period['start']} through {period['end']} (inclusive). "
        f"Punctual means strictly less than {report['punctual_threshold_minutes']} minutes late. "
        "I5 uses the preregistered interval [80%, 99%]. It counts regular, stopping train "
        "arrivals with REAL status and both planned and actual arrival times. It excludes "
        "cancellations and arrivals whose planned or actual arrival falls in the ambiguous "
        "DST hour. A cancellation has no observed delay for I5. In SRQ3 it counts as a "
        "missed connection under D-023.",
        "",
        "Product, anomaly and DST counts cover all stop-event rows in the study period. "
        "Timestamp anomaly counts compare available timestamps, including forecasts.",
        "",
        "Arrival-status shares cover rows with a planned arrival across all products. "
        "The list of operators below 50% REAL coverage applies the study product, "
        "additional-trip and pass-through filters.",
        "",
        f"Stop-event rows without a planned arrival: {report['rows_without_planned_arrival']:,}.",
    ]
    if report["status_basis"] == "parquet_normalized":
        lines.extend(
            [
                "",
                "Original blank statuses are folded into FORECAST where the source "
                "CSVs are unavailable. The empty row counts only blanks present in Parquet.",
            ]
        )
    else:
        lines.extend(["", "Blank arrival statuses are recovered from the matching local CSVs."])

    def table(title: str, headers: tuple[str, ...], rows: list) -> None:
        lines.extend(["", f"## {title}", ""])
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for row in rows:
            cells = [str(value).replace("|", r"\|").replace("\n", "<br>") for value in row]
            lines.append("| " + " | ".join(cells) + " |")

    table(
        "Cumulative filters",
        ("Filter", "Before", "After"),
        [tuple(row.values()) for row in report["filters"]],
    )
    table(
        "Product counts",
        ("PRODUKT_ID", "VERKEHRSMITTEL_TEXT", "Rows"),
        [tuple(row.values()) for row in report["products"]],
    )
    table(
        "Arrival status by operator and product",
        ("Operator", "Product", "Status", "Rows", "Share"),
        [
            (r["operator"], r["product"], r["status"] or "(empty)", r["rows"], f"{r['share']:.2%}")
            for r in report["arrival_status"]
        ],
    )
    table(
        "Operators with less than 50% REAL arrival coverage",
        ("Operator", "Rows", "REAL share"),
        [(r["operator"], r["rows"], f"{r['real_share']:.2%}") for r in report["low_real_coverage"]],
    )
    table("Anomalies and flagged rows", ("Condition", "Rows"), list(report["anomalies"].items()))
    table(
        "Ambiguous DST hour on 2026-10-25, 02:00–02:59 local",
        ("Operator", "Rows"),
        [tuple(row.values()) for row in report["ambiguous_dst"]],
    )
    lines.extend(
        ["", "A row is counted once if any of its four timestamps falls in either fold.", ""]
    )
    lines.extend(f"- {name} {version}" for name, version in report["versions"].items())
    return "\n".join(lines) + "\n"


def build_quality_report(
    interim_dir: Path, config_path: Path, out_md: Path, out_json: Path
) -> dict:
    """Read interim/ist Parquet and study YAML, write Markdown and JSON, and return the report.

    Counts refer to stop-event rows, coverage is a proportion in [0, 1], and delays use
    elapsed minutes. I5's value is null if there are no measurable arrivals.
    """
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    with duckdb.connect() as connection:
        connection.execute(f"SET TimeZone = '{TZ}'")
        _open_events(connection, interim_dir)
        i5, filters = _punctuality(connection, config)
        diagnostics = _diagnostics(connection, config, interim_dir)
    report = {
        "I5": i5,
        "period": {key: str(value) for key, value in config["data"]["period"].items()},
        "punctual_threshold_minutes": config["crisp_baseline"]["punctual_threshold_minutes"],
        "filters": filters,
        **diagnostics,
        "versions": {
            "duckdb": duckdb.__version__,
            "pyarrow": pyarrow.__version__,
            "pyyaml": yaml.__version__,
        },
    }
    for output, content in (
        (out_md, _markdown(report)),
        (out_json, json.dumps(report, ensure_ascii=False, indent=2) + "\n"),
    ):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
    return report
