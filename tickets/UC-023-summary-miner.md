---
id: UC-023
title: Summary miner over segments (Q x S x R enumeration)
epic: fuzzy
milestone: M1
status: todo
owner: agent
estimate_h: 3
depends_on: [UC-020, UC-021]        # hard: needs merged code
soft_depends_on: [UC-022]   # soft: interface exists; integrate when merged
agent: claude
touches: [src/urban_computing/fuzzy/miner.py, src/urban_computing/evaluation/segments.py, scripts/mine_summaries.py, tests/test_miner.py]
realdata: false
---

## Goal
Given a table and a vocabulary, enumerate all summaries for chosen restrictions and return
records with truth, coverage and Qc.

## Outputs
- `mine(values: dict[str, np.ndarray], restrictions: dict[str, np.ndarray], vocab, beta)
  -> list[SummaryRecord]` (pure, NumPy in / records out)
- `evaluation/segments.py`: builds restriction masks from arrivals.parquet
  (network, operator, product, line, canton, time_band, weekday group, half)
- `scripts/mine_summaries.py` → `data/processed/summaries.parquet`
- SummaryRecord schema = PROJECT.md §5 (+ rendered English sentence)

## Acceptance criteria
- [ ] Every record's truth recomputes from the stored masks (spot-check 100 random)
- [ ] Sentence rendering is template-based and deterministic ("About half of the IC
      arrivals in the morning peak are slightly late")
- [ ] Segments with n < 30 arrivals are kept but flagged `small_n`
- [ ] Runtime for all segments of 28 days < 20 min on the VM
- [ ] `make mine` works
- [ ] `SummaryRecord.n` counts complete (non-NaN) rows; the miner output reports dropped rows per segment (e.g. cancelled arrivals) (PM review of #39)

## Tests
`tests/test_miner.py`: fixture with known proportions → expected valid set at β = 0.6;
rendering snapshots.
