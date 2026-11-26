# One entry point for humans and coding agents. Every ticket's tests run under `make check`.
.PHONY: install check lint test test-realdata eval eval-sample board-dry-run clean-results \
	realdata-status data-download data-verify data-ingest data-quality data-arrivals \
	data-connections mine questions llm-collect ablations paper-numbers dispatch-plan \
	codex-next codex-loop

install:
	uv sync --locked --extra dev

lint:
	uv run --locked --extra dev ruff check .
	uv run --locked --extra dev ruff format --check .

test:
	uv run --locked --extra dev pytest -m "not realdata and not gpu"

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

dispatch-plan:
	python3 scripts/dispatch.py plan --dry-run

# ---- Real-data steps (docs/REALDATA_RUNS.md). Each needs the script its ticket creates.
need = @test -f $(1) || { echo "$(1) missing: ticket $(2) not merged yet"; exit 1; }

realdata-status:
	@for pair in download_data.py:UC-010 ingest.py:UC-011 data_quality.py:UC-012 \
	  build_arrivals.py:UC-013 build_connections.py:UC-014 mine_summaries.py:UC-023 \
	  make_questions.py:UC-033 run_llm.py:UC-040 collect_llm.sh:UC-040 \
	  export_paper_numbers.py:UC-070; do \
	  f=$${pair%%:*}; t=$${pair##*:}; \
	  if [ -f scripts/$$f ]; then echo "ready    $$f ($$t)"; else echo "waiting  $$f ($$t)"; fi; \
	done

data-download:
	$(call need,scripts/download_data.py,UC-010)
	uv run python scripts/download_data.py --period 2026-10-01:2026-10-28

data-verify:
	$(call need,scripts/download_data.py,UC-010)
	uv run python scripts/download_data.py --verify

data-ingest:
	$(call need,scripts/ingest.py,UC-011)
	uv run python scripts/ingest.py

data-quality:
	$(call need,scripts/data_quality.py,UC-012)
	uv run python scripts/data_quality.py

data-arrivals:
	$(call need,scripts/build_arrivals.py,UC-013)
	uv run python scripts/build_arrivals.py

data-connections:
	$(call need,scripts/build_connections.py,UC-014)
	uv run python scripts/build_connections.py

mine:
	$(call need,scripts/mine_summaries.py,UC-023)
	uv run python scripts/mine_summaries.py

questions:
	$(call need,scripts/make_questions.py,UC-033)
	uv run python scripts/make_questions.py

llm-collect:
	$(call need,scripts/collect_llm.sh,UC-040)
	bash scripts/collect_llm.sh

ablations:
	uv run python -m urban_computing.evaluation.run --config config/study.yaml --only ablations

paper-numbers:
	$(call need,scripts/export_paper_numbers.py,UC-070)
	uv run python scripts/export_paper_numbers.py

# Local Codex runner (scripts/codex_local.py): one ready Codex ticket -> worktree -> PR.
CODEX_RUN = uv run --no-project --with pyyaml python scripts/codex_local.py
codex-next:
	$(CODEX_RUN)

codex-loop:
	$(CODEX_RUN) --loop
