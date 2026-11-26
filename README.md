# urban-computing

**"At risk for whom?"** An explainable Swiss public-transport assistant built on fuzzy
linguistic summaries (Computing with Words).
Seminar Urban Computing, Human-IST, University of Fribourg, AS-2026.

A commuter asks whether their connection is reliable. The assistant answers with a decision
word (*safe / at risk / risky*) and an explanation in quantified sentences whose truth is
computed from open Swiss transport data. We also test whether an LLM that phrases such
answers stays truthful, using a crisp and a fuzzy checker.

- Project spec: [docs/PROJECT.md](docs/PROJECT.md)
- For coding agents: [AGENTS.md](AGENTS.md)
- Tickets: [tickets/](tickets/) (mirrored on the GitHub Project board)
- Decisions: [docs/decisions.md](docs/decisions.md)
- Evaluation: [docs/evaluation.md](docs/evaluation.md), [eval/hypotheses.yaml](eval/hypotheses.yaml)

## Quick start

```bash
make install       # needs uv
make check         # lint + tests
make eval-sample   # full pipeline on synthetic data
```

Real data: see [docs/data.md](docs/data.md) and ticket UC-010.

## Data source

Ist-Daten and service-point data: opentransportdata.swiss (open use, must provide the
source). No data is stored in this repository.
