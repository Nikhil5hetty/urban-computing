# Installation (prototype)

Swiss public-transport assistant: Streamlit prototype (UC-060). These steps go from a clean
machine to the running app on the **synthetic sample data** (the test fixture), in five
commands. Real data needs the data pipeline first (see the end of this page).

Requirements: macOS, Linux or Windows (WSL) with `git` and an internet connection. Nothing
else: `uv` installs a suitable Python (≥ 3.11) and all packages.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh          # 1. install uv (or: brew install uv)
git clone https://github.com/Nikhil5hetty/urban-computing.git   # 2. get the code
cd urban-computing                                         # 3.
uv sync                                                    # 4. Python + packages (pinned by uv.lock)
uv run streamlit run app/main.py -- --sample               # 5. start the app on the sample data
```

Step 5 prints a local URL (default http://localhost:8501); open it in a browser. The yellow
banner "Synthetic sample data (test fixture), not real measurements." confirms the sample
mode. Stop the app with `Ctrl+C`.

## Real data

After the data steps in `docs/REALDATA_RUNS.md` (`make data-download`, `make data-ingest`,
`make data-arrivals`, `make data-connections`) have written `data/processed/`, start the app
without `--sample`:

```bash
uv run streamlit run app/main.py
```

## Screenshots for the paper

```bash
uv run streamlit run app/main.py --server.headless true --server.port 8599 \
    --theme.base light --client.toolbarMode minimal -- --sample &
uv run python app/screenshots.py --url http://localhost:8599   # needs Google Chrome
```

writes `paper/figures/app_{form,answer,official,chatbot}.png`.

## Troubleshooting

- `command not found: uv` after step 1: open a new terminal (the installer adds uv to the
  PATH of new shells).
- Port 8501 in use: add `--server.port 8502` before `--` in step 5.
- The app never calls a language model. The "Chatbot view" shows cached answers only, which
  exist once the LLM runs (UC-040) have been collected.
