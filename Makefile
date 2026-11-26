# One entry point for humans and coding agents. Every ticket's tests run under `make check`.
.PHONY: install check lint test test-realdata eval eval-sample board-dry-run clean-results

install:
	uv sync --extra dev

lint:
	uv run ruff check .
	uv run ruff format --check .

test:
	uv run pytest -m "not realdata and not gpu"

# Task-level gate: must be green before any PR is opened.
check: lint test

# Tests that need the downloaded Ist-Daten (run locally / on UBELIX, never in CI).
test-realdata:
	uv run pytest -m realdata

# Project-level evaluation (UC-053): recomputes every number and checks it against
# eval/hypotheses.yaml. Writes results/results.json and results/REPORT.md.
eval:
	uv run python -m urban_computing.evaluation.run --config config/study.yaml

# Same pipeline on the synthetic fixture in tests/fixtures (fast, CI-safe).
eval-sample:
	uv run python -m urban_computing.evaluation.run --config config/study.yaml --sample

board-dry-run:
	python3 scripts/bootstrap_github.py --dry-run

clean-results:
	rm -rf results/*.json results/*.md results/figures results/tables
