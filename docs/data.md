# Data

All data is public, used as published, and **never committed** to git. Raw files are
read-only (AGENTS.md §4). Cite the source in the paper, README and prototype footer.

## 1. Ist-Daten v2 (actual data), opentransportdata.swiss

- Dataset page (current month): https://data.opentransportdata.swiss/dataset/ist-daten-v2
- Archive (daily files bundled per month as ZIP, 2016 → last complete month):
  [Ist-Daten archive index](https://archive.opentransportdata.swiss/istdaten.php).
  The v2 path is `/istdaten/YYYY/ist-daten-v2-YYYY-MM.zip`. The study uses
  [ist-daten-v2-2026-10.zip](https://archive.opentransportdata.swiss/istdaten/2026/ist-daten-v2-2026-10.zip).
  The ZIP lists `2026-10-DD_IstDaten.csv` for days 01–28, except day 12, which is
  `2026-10-12_istdaten.csv`. The downloader keeps the ZIP and extracts the requested days.
- Cookbook (field definitions): https://opentransportdata.swiss/en/cookbook/historic-and-statistics-cookbook/actual-data/
- Terms: "Open use. Must provide the source." (opendata.swiss listing)
- Period used: 1–28 Oct 2026 (D-005). Size: several hundred MB per day as CSV.

### Fields used

| Field | Meaning | Notes |
|---|---|---|
| BETRIEBSTAG | operating day | DD.MM.YYYY, may be non-zero-padded |
| FAHRT_BEZEICHNER | journey id | |
| BETREIBER_ABK / BETREIBER_NAME | operator | |
| PRODUKT_ID | means of transport (train, bus, …) | exact strings to be listed in UC-012 |
| LINIEN_TEXT | customer-facing line name | |
| VERKEHRSMITTEL_TEXT | form of transport (IC, IR, RE, S, …) | |
| ZUSATZFAHRT_TF | extra journey not in timetable | null = false |
| FAELLT_AUS_TF | journey cancelled | null = false |
| BPUIC / SLOID | stop id | v2: BPUIC may be 7-digit, 9-digit or a SLOID |
| HALTESTELLEN_NAME | stop name | may differ from master data; may be blank |
| ANKUNFTSZEIT / ABFAHRTSZEIT | planned arrival/departure | DD.MM.YYYY HH24:MI (minute precision) |
| AN_PROGNOSE / AB_PROGNOSE | actual or forecast time | DD.MM.YYYY HH24:MI:SS |
| AN_PROGNOSE_STATUS / AB_PROGNOSE_STATUS | REAL, ESTIMATED, FORECAST, UNKNOWN, empty (= FORECAST) | keep REAL only (D-006) |
| DURCHFAHRT_TF | passes without stopping | excluded |

### Known quirks (cookbook)

- Actual times are often not available; the last forecast is used instead → filter on REAL.
- Special effects: departures before arrivals, departures before timetable, implausible
  border times. UC-012 counts each and documents handling.
- v2 (from 13 Jul 2025) adds foreign stops; international journeys may be cut at borders.
- The CSV separator and encoding must be detected in UC-011 (cookbook example uses commas;
  other sources mention `;`).

## 2. Service points (atlas v2), opentransportdata.swiss

- https://data.opentransportdata.swiss/dataset/service-point-v2
  (`actual-date-swiss-service-point.csv`)
- Use: stop names, SLOID/number mapping, canton, coordinates for regional restrictions and
  the hub lookup. Terms: open use, must provide the source.

## 3. Reference figures (sanity only)

- SBB punctuality definition: a train is punctual if it arrives < 3 min late.
- SBB reported ~94% passenger-train punctuality for 2025 (`TODO(verify)` against the SBB
  press release before citing). Different scope (SBB only, customer-weighted) → I5 uses a
  wide band.

## 4. Manifest

UC-010 writes `data/MANIFEST.json`:
`{files: [{path, url, sha256, bytes, downloaded_at}], source, terms}`. Invariant I3 checks it.
Paths are relative to the manifest directory. Daily CSV entries point to their source ZIP.
Run `make data-download` and `make data-verify` on the real-data machine (A1–A2 in
[REALDATA_RUNS.md](REALDATA_RUNS.md)). Preview the two source URLs with
`uv run python scripts/download_data.py --period 2026-10-01:2026-10-28 --dry-run`.
Downloads are staged outside `data/raw/` and published as read-only files. A rerun
reuses files that match the manifest. A checksum mismatch stops the run and identifies
the existing file for review. The manifest records the direct
[service-point CSV URL](https://data.opentransportdata.swiss/dataset/39e5f264-257a-4f3f-bccc-5322c37058c5/resource/38ae9c04-05e4-4420-8c56-250ac6f4eb2f/download/actual-date-swiss-service-point.csv).

## 5. Daily CSV ingestion (UC-011)

`make data-ingest` reads the case-insensitive `.csv` entries in `data.raw_dir` from
`config/study.yaml`, ignores the ZIP, and writes one file per operating day under
`data.interim_dir/ist/`. Each CSV record becomes one row in the frozen `STOP_EVENTS`
schema, with its original filename and zero-based record index. The CSV columns are
bound by name. The leading `_id` is optional, and an absent `SLOID` maps to null.
BPUIC and SLOID are kept as text, including leading zeros.

The importer detects the separator from the header and tries UTF-8 first unless a
Unicode BOM is present. For other files it tries Windows-1252, then ISO-8859-1. Those
legacy encodings share many byte values, so the report records the chosen decoder.
DuckDB streams one day at a time and PyArrow writes bounded batches. Parquet stores
Europe/Zurich timezone metadata. Empty flags become false and empty forecast statuses
become `FORECAST`. Invalid nonblank timestamps become null. Missing required headers and
malformed CSV records fail ingestion.

`data/interim/ingest_report.json` contains library versions and a `files` array with row
counts, separator, encoding, parse-failure counts by output column, and normalized
status counts keyed as `column:status`.

### First real-day header comparison

```sh
uv run --locked --extra dev pytest -m realdata -s tests/test_ingest.py
make data-ingest
```

The smoke test compares the first local daily CSV header to the UC-004 fixture, prints
the field-by-field diff, and verifies the written row count against a separate CSV
record count. **TODO(verify)** Record the observed header diff and detected separator
and encoding here during real-data Batch A.

## 6. Hub connections (UC-014)

The builder resolves configured hubs against the Swiss atlas service-point export using
the official designation. It matches STOP_EVENTS by stop-level SLOID or DiDok number,
including child SLOIDs. The builder matches nine-digit BPUICs by their first seven
digits. **TODO(verify)** Confirm this mapping against the published identifier
definition. The STOP_EVENTS display name does not affect matching. The log records the identifiers resolved from the input export.
[Atlas service-point field definitions](https://opentransportdata.swiss/en/cookbook/masterdata-cookbook/servicepoints/).

| Hub | DiDok number | Stop SLOID |
|---|---|---|
| Zürich HB | `8503000` | `ch:1:sloid:3000` |
| Bern | `8507000` | `ch:1:sloid:7000` |
| Olten | `8500218` | `ch:1:sloid:218` |

[Zürich HB identifiers](https://opentransportdata.swiss/en/cookbook/timetable-cookbook/gtfs/),
[Bern identifiers](https://data.sbb.ch/explore/dataset/linie-mit-betriebspunkten/table/),
[Olten identifiers](https://data.sbb.ch/explore/dataset/ist-daten-sbb/api/?flg=de-ch).

DuckDB filters to in-scope hub stops and range-joins planned arrivals to departures
2–15 minutes later, inclusive, from different journeys. Operating day, weekday and study
half come from A. The time band comes from A's planned local arrival. An uncancelled
arrival and departure require a REAL status and timestamp. A cancelled departure can
pair with a REAL arrival and has null actual gap and departure delay. Pairs with a
cancelled feeder A are excluded. SRQ2 therefore omits transfers missed because the
feeder was cancelled.

Following the proposed D-025 extension of D-024, otherwise eligible pairs are retained
as unknown when A's planned or actual arrival or B's planned or actual departure is in
`[2026-10-25 00:00, 2026-10-25 02:00) UTC`, covering both folds of the repeated
local hour. Their actual gap and both delays are null and `b_cancelled` is false.
Gaps and delays use elapsed minutes. A negative actual gap means B left before A arrived. To compute
slack, subtract the assumed transfer time from the actual gap (D-009). The source
provides neither passenger transfer choices nor platform-specific walking times.

`data/processed/connections_log.json` reports counts by hub and A's operating day,
omitting dates with zero candidates. Each candidate is counted once, in order, as
`a_cancelled`, `a_not_real`, `b_not_real`, `dst_excluded`, or `retained`.
`dst_excluded` counts the same unknown pairs as `ambiguous_dst_pairs` and refers to
exclusion from REAL measurements. `pairs` counts all output rows, including the DST
pairs. The hub-level REAL share divides the number of uncancelled pairs with usable
REAL timestamps on both sides by the number of planned candidates. The three-day synthetic fixture has 25 retained pairs
at Zürich HB (8–9 per day) and four at Olten (one to two per day). Bern has no fixture pairs.

### 28-day VM check

With the local atlas export and all 28 ingested STOP_EVENTS files in place, run:

```sh
time make data-connections
python3 -m json.tool data/processed/connections_log.json
```

**TODO(verify, UC-014)** Record the wall time against the 15-minute target and the observed
candidate and retained counts per hub per day. The ticket expects thousands of pairs
per hub per day. Confirm that the logged identifiers match the table above.
