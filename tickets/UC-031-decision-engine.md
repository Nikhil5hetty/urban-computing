---
id: UC-031
title: Perception-aware connection-risk decision with faithful explanation
epic: assistant
milestone: M2
status: todo
owner: agent
estimate_h: 4
depends_on: [UC-030, UC-023, UC-014]
touches: [src/urban_computing/assistant/engine.py, tests/test_engine.py, docs/methods.md, config/vocabulary.yaml]
realdata: false
---

## Goal
`answer(question, connections, arrivals, vocab) -> Answer`. The decision word and the
explanation sentences come from the same truth computation (invariant I4). This is the CWW
core: encoder (data → fuzzy words) → engine (quantified truth) → decoder (decision word).

## Draft rule (finalise in docs/methods.md §5 and log a decision)
1. Select the segment: connections at `hub` matching the question (fallback: arrivals of
   the arriving line at the hub if fewer than 20 connections; flag `fallback=true`).
2. Encoder: per observation, μ_missed(slack) and μ_tight(slack) from
   `connection_slack_minutes`; in the fallback, μ = late_for_my_transfer(delay; margin).
3. Fuzzy proportion p_miss = mean(μ_missed) (and p_tight).
4. Decoder: decision words are fuzzy sets over p_miss — suggested
   safe [null, null, 0.05, 0.10], at_risk [0.05, 0.10, 0.20, 0.30], risky [0.20, 0.30, null, null];
   decision = argmax membership (ties → the more cautious word).
5. Explanation: the quantified sentence for p_miss ("Few of your connections are missed")
   plus up to 3 highest-Qc valid summaries for the same segment, each with truth, coverage, n.

## Acceptance criteria
- [ ] I4: for every Answer on the fixture and question set, each explanation's truth
      recomputes from the stored segment to < 1e-9 (`verify_answer(answer, data) -> bool`)
- [ ] Decision changes monotonically: increasing delays never makes the word safer
- [ ] Margin matters: same data, margin 3 vs 10 min gives a different word on the
      borderline fixture segment
- [ ] Explanations never state a sentence with truth < β
- [ ] Decision rule + thresholds documented in docs/methods.md §5 with rationale

## Tests
`tests/test_engine.py`: monotonicity, margin effect, I4 checker on fixture, small-n fallback.
