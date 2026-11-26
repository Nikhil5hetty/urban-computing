# Project specification

**Working title:** *"At risk for whom?" An explainable Swiss public-transport assistant built
on fuzzy linguistic summaries*

**Course:** Seminar Urban Computing (UE-SIN.07832), Human-IST / Resilient Systems group,
University of Fribourg, AS-2026. Paper follows the Human-IST seminar guidelines
(ACM acmart single-column, 16–30 pages, concept part + practical part, prototype docs in
appendix, GenAI declaration).

**Deliverables (6 Dec 2026):** (1) this repository with a working prototype and
reproducible evaluation, (2) seminar paper, (3) slide deck (owner: Nikhil).

## 1. Problem

Official punctuality figures use a crisp rule (SBB: a train is punctual if it is less than
3 minutes late) and are reported network-wide. Passenger research shows people judge
"on time" more strictly than industry standards and care most about the certainty of their
own trip and connections. A commuter cannot get an honest, plain-language answer about
*their* train and *their* connection. Chatbots are an obvious interface, but their wording
("most", "a few", "slightly late") is unchecked even when the numbers they query are right.

## 2. Contribution

1. A **CWW engine** (fuzzy linguistic summaries with Hudec quality) on public Swiss
   Ist-Daten, with the Pincay et al. (2021) configuration as baseline.
2. An **explainable assistant** whose decision word and explanation come from the same
   truth computation (faithful by construction), with a perception-aware notion of "late"
   that depends on the passenger's own transfer margin.
3. Empirical answers to SRQ1–SRQ3 (see eval/hypotheses.yaml), including a fuzzy-vs-crisp
   audit of LLM-written claims that extends Stat-to-Text (Eida et al., 2026) to vague
   quantifiers, graded truth and real data.

## 3. Research questions

| ID | Citizen question | Research question | Hypotheses |
|---|---|---|---|
| Main | — | Can fuzzy linguistic summaries be the explainable core of a citizen-facing assistant that answers questions about the reliability of Swiss public-transport trips? | answered by SRQ1–3 + invariants |
| SRQ1 | "Is the answer about my trip?" | With coverage and regional quality measures (Hudec), which summaries still hold for a citizen's own line/station/time, and how often do network-wide summaries mask local reality? | H1a, H1b, H1c |
| SRQ2 | "At risk for whom?" | How often does the crisp official view give a different connection verdict than a perception-aware view based on the passenger's transfer margin? | H2a, H2b |
| SRQ3 | "Can I trust the chatbot?" | Are LLM-written quantified claims faithful to the data, does fuzzy grounding help, and where do crisp and fuzzy checkers disagree? | H3a, H3b, H3c |

## 4. Architecture and data flow

```
data/raw/ist-daten/*.csv (READ-ONLY)        data/raw/service-points/*.csv
        │ UC-011 ingest + validate                     │
        ▼                                              ▼
data/interim/ist/*.parquet ──UC-012 quality report──► docs/data-quality.md
        │ UC-013
        ▼
data/processed/arrivals.parquet  ──UC-014──►  data/processed/connections.parquet
        │                                           │
        ▼                                           ▼
   fuzzy/ vocabulary (UC-020) → truth engine (UC-021) → quality (UC-022) → miner (UC-023)
        │                                           │
        ├── baseline Pincay config (UC-024)         │
        ▼                                           ▼
   assistant/ contract (UC-030) → fuzzy decision + explanation (UC-031) ← crisp baseline (UC-032)
        │                       question set (UC-033) → eval/questions.jsonl
        ▼
   llm/ runner on UBELIX (UC-040) → claim parser (UC-041) → crisp + fuzzy checkers (UC-042)
        │
        ▼
   evaluation/ SRQ1 (UC-050), SRQ2 (UC-051), SRQ3 (UC-052), ablations (UC-054)
        │
        ▼
   project runner `make eval` (UC-053) → results/results.json, results/REPORT.md
        │                                   │
        ▼                                   ▼
   prototype app (UC-060)            paper/numbers.tex (UC-070) → paper (UC-071/072)
```

## 5. Interfaces (contracts every ticket must respect)

The executable source of truth is code, not this list: table schemas in
`src/urban_computing/data/schemas.py`, function signatures in the module stubs (guarded by
`tests/test_interfaces.py`), and `tests/factories.py` to build schema-correct test data.
Connections are built from STOP_EVENTS (interim), because departures are needed.

- **arrivals.parquet** (UC-013): one row per REAL train arrival at a stop.
  Columns: `operating_day (date)`, `journey_id (str)`, `operator_abbr (str)`,
  `product (str)`, `line (str)`, `stop_id (str)`, `stop_name (str)`, `canton (str|null)`,
  `planned_arrival (timestamp)`, `actual_arrival (timestamp)`, `delay_min (float)`,
  `cancelled (bool)`, `time_band (str)`, `weekday (int 0=Mon)`, `half (first|second)`.
- **connections.parquet** (UC-014): one row per observed A→B pair at a hub.
  Columns: `hub`, `operating_day`, `arr_journey_id`, `dep_journey_id`, `arr_product`,
  `dep_product`, `arr_line`, `dep_line`, `planned_gap_min`, `actual_gap_min`,
  `arr_delay_min`, `dep_delay_min`, `time_band`, `weekday`, `half`.
- **Summary record** (UC-023, JSON): `{protoform, quantifier, summarizer, restriction,
  segment, n, truth, coverage, quality, half}`.
- **Answer** (UC-030, pydantic): `decision`, `explanations[]` (each a Summary record plus
  rendered sentence), `crisp_decision`, `question`, `provenance` (data period, config hash).
- **results.json** (UC-053): `{hypotheses: {H1a: {point, ci_low, ci_high, p, verdict}},
  invariants: {I1: pass|fail}, tables: {...}, meta: {git_sha, config_hash, versions}}`.

## 6. Milestones

| Milestone | Due | Exit criterion |
|---|---|---|
| M1 Data + fuzzy core | Sun 29 Nov | arrivals + connections built on real data; truth engine passes I1, I2; baseline table |
| M2 Assistant + SRQ1/2 | Wed 2 Dec | assistant answers the question set; I4 passes; H1*, H2* computed |
| M3 LLM audit + prototype | Fri 4 Dec | H3* computed; prototype runs; `make eval` produces full REPORT.md |
| M4 Paper + submission | Sun 6 Dec | paper compiled with numbers from results.json; slides; submission package |

## 7. Roles

- **PM (Claude in the claude.ai Project):** owns tickets, decisions, reviews PRs, verifies numbers.
- **Coding agents (Codex, Claude Code):** implement tickets, one PR each.
- **Nikhil:** merges, runs real-data and UBELIX jobs, owns the slide deck, talks to the TA.

## 8. Out of scope (unless a decision adds it)

Interval type-2 quantifiers; second LLM family; new human data or user studies; passenger
counts; causal explanations of delays; German/French UI.
