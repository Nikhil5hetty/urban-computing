# Data-quality report

**I5 FAIL** · 50.00% (16 of 32 arrivals)

> Generated from the checked-in synthetic fixture. The fixture deliberately contains many arrivals at the three-minute boundary.
> **TODO(verify)** Confirm the real-data product strings and the 28-day runtime.
> To replace this example with the study report, run `make data-ingest` on local study CSVs, then run `time make data-quality` on the VM.

Operating days 2026-10-01 through 2026-10-28 (inclusive). Punctual means strictly less than 3 minutes late. I5 uses the preregistered interval [80%, 99%]. It counts regular, stopping train arrivals with REAL status and both planned and actual arrival times. It excludes cancellations and arrivals whose planned or actual arrival falls in the ambiguous DST hour. A cancellation has no observed delay for I5. In SRQ3 it counts as a missed connection under D-023.

Product, anomaly and DST counts cover all stop-event rows in the study period. Timestamp anomaly counts compare available timestamps, including forecasts.

Arrival-status shares cover rows with a planned arrival across all products. The list of operators below 50% REAL coverage applies the study product, additional-trip and pass-through filters.

Stop-event rows without a planned arrival: 32.

Blank arrival statuses are recovered from the matching local CSVs.

## Cumulative filters

| Filter | Before | After |
| --- | --- | --- |
| period | 67 | 67 |
| scope_products | 67 | 67 |
| exclude_additional_trips | 67 | 67 |
| exclude_pass_through | 67 | 66 |
| has_arrival | 66 | 35 |
| keep_status | 35 | 32 |
| measurable_real_arrival | 32 | 32 |

## Product counts

| PRODUKT_ID | VERKEHRSMITTEL_TEXT | Rows |
| --- | --- | --- |
| Zug | IC | 26 |
| Zug | S | 41 |

## Arrival status by operator and product

| Operator | Product | Status | Rows | Share |
| --- | --- | --- | --- | --- |
| TEST | Zug | (empty) | 0 | 0.00% |
| TEST | Zug | ESTIMATED | 1 | 2.86% |
| TEST | Zug | FORECAST | 1 | 2.86% |
| TEST | Zug | REAL | 32 | 91.43% |
| TEST | Zug | UNKNOWN | 1 | 2.86% |

## Operators with less than 50% REAL arrival coverage

| Operator | Rows | REAL share |
| --- | --- | --- |

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
