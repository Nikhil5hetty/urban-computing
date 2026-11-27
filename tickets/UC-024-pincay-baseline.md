---
id: UC-024
title: Pincay et al. (2021) configuration as methodological baseline
epic: fuzzy
milestone: M1
status: done
owner: agent
estimate_h: 1
depends_on: [UC-023]        # hard: needs merged code
soft_depends_on: [UC-013]   # soft: interface exists; integrate when merged
agent: codex
touches: [src/urban_computing/evaluation/baseline.py, tests/test_baseline.py]
realdata: true
---

## Goal
Run the original configuration (no restrictions, quantifiers few/about half/most, four
delay words, β = 0.6, truth only) network-wide, so SRQ1 can show what changes when quality
and restrictions are added.

## Outputs
`results/tables/baseline_pincay.csv` (12 rows: 3 Q × 4 S, truth, valid flag) via the
evaluation runner, plus the same table per half.

## Acceptance criteria
- [x] Table has exactly 12 rows per half, layout like Pincay et al. Table 1
- [x] Paper text calls it a "methodological baseline" (D-003); no comparison of numbers
      with their traffic-message data
- [x] Registered as an experiment in the project runner (UC-053)
- [x] D-028: use Pincay et al.'s own quantifier curves from their Fig. 2 (few [−∞,−∞,0.2,0.4], about_half [0.2,0.4,0.6,0.8], most [0.6,0.8,+∞,+∞]; methods §1) via a config override, not our study vocabulary; state the difference in the table caption (UC-002)

## Tests
`tests/test_baseline.py` on the fixture.

## Real-data run

After Batch A has produced `data/processed/arrivals.parquet`, run:

```sh
uv run --locked python -m urban_computing.evaluation.run --config config/study.yaml --only baseline
wc -l results/tables/baseline_pincay.csv results/tables/baseline_pincay_first.csv results/tables/baseline_pincay_second.csv
```

Expect 13 lines per file, including the header. A half with no measured delays has blank
truth values and all validity flags are false.

## Manuscript wording for UC-071 and UC-072

**Methods.** We apply the unrestricted truth computation of Pincay et al. (2021, Eq. 2)
as a methodological baseline for Swiss train arrival delays. The analysis uses the Swiss
Ist-Daten arrivals and the study's four arrival-delay membership functions.

**Table caption.** Methodological baseline for Swiss train arrivals. Truth uses the
quantifier curves from Pincay et al. (2021, Fig. 2, p. 172), whose breakpoints differ
from those of the main study vocabulary (D-028). A summary is valid at truth ≥ 0.6.


## Review scope exceptions

The PM review explicitly requested manuscript integration to complete this ticket's
acceptance criteria. `paper/sections/concept.tex` now contains the methodological
baseline description, and `paper/sections/results.tex` contains the baseline layout
and caption explaining the Figure 2 quantifier difference. Study values remain pending
Batch A and must come from runner outputs; the table uses explicit pending placeholders.
The dedicated `config/vocabulary.yaml` override is authorized by accepted D-028 and
the owner's review; the main-study curves are unchanged.
