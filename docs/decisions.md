# Decision log

Status values: `accepted` (binding), `proposed` (awaiting PM), `rejected`, `superseded`.
Agents may add `proposed` entries; only the PM/Nikhil set `accepted`.

| ID | Date | Status | Decision | Rationale / source |
|---|---|---|---|---|
| D-001 | 2026-11-26 | accepted | New repo `urban-computing`; previous mental-health project is not continued here. | Professor feedback: no alignment with course; topic restarted in the professor/TA domain (fuzzy systems, CWW). |
| D-002 | 2026-11-26 | accepted | Topic: explainable citizen-facing Swiss public-transport assistant; fuzzy linguistic summaries are the CWW/XAI core. Covers urban mobility, citizen service and resilience (connection reliability). | Course description ("citizen-centered … computing with words and perception services", Swiss network industries incl. transport); LS as XAI: Wrede et al. 2023; Kaczmarek-Majer et al. 2022 (PLENARY). |
| D-003 | 2026-11-26 | accepted | Pincay, Portmann & Terán (2021) is re-implemented as a **baseline** only (methodological, their data is not public); it is not a research question. | Paper gives no code/data link; membership functions only as figures. |
| D-004 | 2026-11-26 | accepted | Only existing published data; no new human data, no user study. Claims are about *verifiable* explanations, not about user understanding. | Seminar constraint; deadline 6 Dec. |
| D-005 | 2026-11-26 | accepted | Data: opentransportdata.swiss Ist-Daten v2, 28 days 1–28 Oct 2026 from the monthly archive; service-point master data (atlas v2) for names/cantons. Trains only in the main study. | Open use, must provide the source. October 2026 is the last complete month in the archive. |
| D-006 | 2026-11-26 | accepted | Only `REAL` arrival/departure status counts as measured. ESTIMATED, FORECAST, UNKNOWN are dropped; drop share is reported by operator and product. | Cookbook: actual times are often not available and the last forecast is used; statistics must account for this. |
| D-007 | 2026-11-26 | accepted | Crisp baseline uses the SBB punctuality definition: < 3 min late = punctual. The fuzzy `on_time` word reaches 0 at 3 min so the two are comparable. | SBB definition. |
| D-008 | 2026-11-26 | accepted | Quantifiers few / about half / most and β = 0.6 as in Pincay et al. 2021; exact breakpoints are ours (draft in config/vocabulary.yaml, finalised in UC-020). | Pincay et al. 2021 give curves only graphically. |
| D-009 | 2026-11-26 | accepted | Connections are reconstructed at three hubs (Zürich HB, Bern, Olten) from arrival/departure pairs with planned gap 2–15 min; minimum transfer time is an assumption (default 2 min, sensitivity 1–4). | Ist-Daten has no planned-connection table. Limitation stated in paper. |
| D-010 | 2026-11-26 | accepted | Perception-aware "late for my transfer" is parameterised by the passenger's margin (3–10 min). Passenger "on time" expectation (~1 min) from published UK passenger research is used for motivation, not as a Swiss parameter. | Transport Focus / ORR 2015. No Swiss perception data; no new elicitation (D-004). |
| D-011 | 2026-11-26 | accepted | LLM: Apertus-8B-Instruct run locally on UBELIX; conditions stats_only and fuzzy_grounded; query-tool condition is stretch (UC-043). One model family only. | Swiss open model; budget/time. |
| D-012 | 2026-11-26 | accepted | Crisp claim checker follows Stat-to-Text truth conditions ("most" = more than half; set-based all/some/no) but is implemented deterministically (no LLM-written checker). | Eida et al. 2026 (arXiv 2609.23966); their checker produced false positives/negatives. |
| D-013 | 2026-11-26 | accepted | Hypotheses and thresholds in eval/hypotheses.yaml are pre-registered at this commit and frozen. | Avoid post-hoc threshold tuning. |
| D-014 | 2026-11-26 | accepted | Name in code, UI and paper: "Swiss public-transport assistant"; no SBB branding. | Data covers all operators; avoid implying an official product. |
| D-015 | 2026-11-26 | accepted | Out of scope: IT2 quantifiers, second LLM, passenger counts, causal delay explanations, multilingual UI. | Scope to 6 Dec. |
| D-016 | 2026-11-26 | accepted | Status of a ticket lives in its file (`status:` field) and is mirrored on the GitHub Project board; the file wins on conflict. | Agents without GitHub auth can still see status. |

## Open questions (for TA / PM)

| ID | Question | Owner | Blocks |
|---|---|---|---|
| Q-001 | Would a short think-aloud walkthrough with 3–5 classmates count as "new human data"? If allowed, it would support an understandability claim. | Nikhil → TA | nothing (optional) |
| Q-002 | Confirm the reframed topic fits the seminar before 29 Nov. | Nikhil → TA | M2 framing |
| Q-003 | Repository licence for code (MIT proposed). | Nikhil | nothing |
