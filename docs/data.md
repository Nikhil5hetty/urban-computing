# Data

All data is public, used as published, and **never committed** to git. Raw files are
read-only (AGENTS.md §4). Cite the source in the paper, README and prototype footer.

## 1. Ist-Daten v2 (actual data), opentransportdata.swiss

- Dataset page (current month): https://data.opentransportdata.swiss/dataset/ist-daten-v2
- Archive (daily files bundled per month as ZIP, 2016 → last complete month):
  https://archive.opentransportdata.swiss/ — the exact file naming must be read off the
  archive page in UC-010 (not documented in the cookbook).
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
