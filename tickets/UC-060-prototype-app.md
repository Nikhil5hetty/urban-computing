---
id: UC-060
title: Prototype app (Streamlit) for citizens
epic: prototype
milestone: M3
status: todo
owner: agent
estimate_h: 4
depends_on: [UC-031, UC-032]
touches: [app/, src/urban_computing/assistant/render.py, tests/test_render.py]
realdata: false
---

## Goal
The design-science artefact: a commuter picks hub, arriving line, departing line, time
band, day and their transfer margin, and gets the decision word with the explanation.

## Screens
1. Question form (dropdowns filled from data; margin slider 2–15 min)
2. Answer: decision badge (safe / at risk / risky), explanation sentences each with truth
   bar, coverage and n ("based on 38 trains"), data period and source footer
3. "Official view" panel: crisp decision + crisp sentences side by side (SRQ2 story)
4. "Chatbot view" panel: cached LLM answer for this question (if in eval set) with
   per-claim truth badges green ≥ 0.6, amber 0.3–0.6, red < 0.3 (SRQ3 story)

## Acceptance criteria
- [ ] Runs with `uv run streamlit run app/main.py` on processed data; on the fixture with
      `--sample`
- [ ] No LLM calls at runtime (uses cached outputs only)
- [ ] Every number shown comes from the Answer object (render tests)
- [ ] Footer: "Data: opentransportdata.swiss (Ist-Daten, Oct 2026)"; no SBB branding (D-014)
- [ ] Screenshots of all 4 views saved to `paper/figures/app_*.png`

## Tests
`tests/test_render.py` (render functions are pure and tested; UI glue not unit-tested).
