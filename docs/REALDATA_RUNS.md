# Real-data runs (Nikhil, on the VM / UBELIX)

Agents finish `realdata: true` tickets on the synthetic fixture. The real runs happen here,
in batches, so no agent waits for downloads, big joins or GPUs. Run a batch whenever the
tickets in it are merged; tick the box and paste the one-line summary (or the PR/issue link
where you pasted the full output).

Each step is a `make` target that the named ticket must create (the target fails with a
clear message until the ticket is merged). `make realdata-status` prints which steps are
runnable.

## Batch A — data (after UC-010…UC-014 merge)

| ✓ | Step | Command | Ticket | Expected output | Summary |
|---|---|---|---|---|---|
| [ ] | A1 download | `make data-download` | UC-010 | `data/MANIFEST.json`, 28 CSV + service points | |
| [ ] | A2 verify | `make data-verify` | UC-010 | `I3 pass` | |
| [ ] | A3 ingest | `make data-ingest` | UC-011 | `data/interim/ist/*.parquet`, rows_in == rows_out | |
| [ ] | A4 quality | `make data-quality` | UC-012 | `docs/data-quality.md` (commit it), `I5 pass/fail` | |
| [ ] | A5 arrivals | `make data-arrivals` | UC-013 | `data/processed/arrivals.parquet` | |
| [ ] | A6 connections | `make data-connections` | UC-014 | `data/processed/connections.parquet` | |
| [ ] | A7 tests | `make test-realdata` | all | all realdata tests green | |

## Batch B — summaries and assistant (after UC-023, UC-024, UC-031…UC-033 merge)

| ✓ | Step | Command | Ticket | Expected output | Summary |
|---|---|---|---|---|---|
| [ ] | B1 mine | `make mine` | UC-023 | `data/processed/summaries.parquet` | |
| [ ] | B2 questions | `make questions` | UC-033 | `eval/questions.jsonl` (commit it) | |

## Batch C — LLM on UBELIX (after UC-040 merge; UC-043 optional)

| ✓ | Step | Command | Ticket | Expected output | Summary |
|---|---|---|---|---|---|
| [ ] | C1 submit | `sbatch slurm/run_llm.sbatch` | UC-040 | jobs for 2 conditions × 2 temps × 3 seeds | |
| [ ] | C2 collect | `make llm-collect` | UC-040 | `data/interim/llm/**.jsonl` synced to the VM | |
| [ ] | C3 query tool | `sbatch slurm/run_llm.sbatch query_tool` | UC-043 | optional | |

## Batch D — evaluation (after UC-050…UC-054 merge)

| ✓ | Step | Command | Ticket | Expected output | Summary |
|---|---|---|---|---|---|
| [ ] | D1 eval | `make eval` | UC-053 | `results/results.json`, `results/REPORT.md` | |
| [ ] | D2 ablations | `make ablations` | UC-054 | `results/tables/ablations.csv` | |
| [ ] | D3 paper numbers | `make paper-numbers` | UC-070 | `paper/numbers.tex` | |

## Rules

- Never edit `data/raw/`. If a step fails because of the data, open an issue with the
  error and the ticket id; do not patch files by hand.
- Paste only summaries here (counts, pass/fail). Do not paste data rows.
- After A4 and B2, commit the generated docs file / question set in a PR titled
  `realdata: batch A` / `realdata: batch B`.
