# Data-quality report

**I5 FAIL** · 50.00% (16 of 32 arrivals)

> Generated from the checked-in synthetic fixture. The fixture deliberately contains many arrivals at the three-minute boundary.
> **TODO(verify)** Confirm the real-data product strings and the 28-day runtime.
> To replace this example with the study report, run `make data-ingest` on local study CSVs, then run `time make data-quality` on the VM.

Operating days 2026-10-01 through 2026-10-28 (inclusive). Punctual means strictly less than 3 minutes late. I5 uses the preregistered interval [80%, 99%]. Its denominator excludes cancelled arrivals, missing arrival timestamps and arrivals in the ambiguous DST hour.

Diagnostic tables count stop-event rows in the study period before product or status filtering. Timestamp anomaly counts compare available timestamps, including forecasts.

Blank arrival statuses are recovered from the matching local CSVs.

## Cumulative filters

| Filter | Before | After |
| --- | --- | --- |
| period | 67 | 67 |
| scope_products | 67 | 67 |
| exclude_additional_trips | 67 | 67 |
| exclude_pass_through | 67 | 66 |
| keep_status | 66 | 32 |
| measurable_real_arrival | 32 | 32 |

## Product counts

| PRODUKT_ID | VERKEHRSMITTEL_TEXT | Rows |
| --- | --- | --- |
| Zug | IC | 26 |
| Zug | S | 41 |

## Arrival status by operator and product

| Operator | Product | Status | Rows | Share |
| --- | --- | --- | --- | --- |
| TEST | Zug | (empty) | 32 | 47.76% |
| TEST | Zug | ESTIMATED | 1 | 1.49% |
| TEST | Zug | FORECAST | 1 | 1.49% |
| TEST | Zug | REAL | 32 | 47.76% |
| TEST | Zug | UNKNOWN | 1 | 1.49% |

## Operators with less than 50% REAL arrival coverage

| Operator | Rows | REAL share |
| --- | --- | --- |
| TEST | 67 | 47.76% |

## Anomalies and flagged rows

| Condition | Rows |
| --- | --- |
| departure_before_arrival | 1 |
| departure_before_planned | 1 |
| arrival_over_6_hours | 0 |
| empty_stop_name | 0 |
| cancelled | 1 |
| pass_through | 1 |

## Ambiguous DST hour on 2026-10-25, 02:00–02:59 local

| Operator | Rows |
| --- | --- |
| TEST | 0 |

A row is counted once if any of its four timestamps falls in either fold.

- duckdb 2.0.1
- pyarrow 26.0.1
- pyyaml 6.0.4
