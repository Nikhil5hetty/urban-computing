# UC-040 Apertus runs on UBELIX

The configured model is `swiss-ai/Apertus-8B-Instruct-2509`. Staging and inference use
the full commit hash from `llm.model_revision` when set in `config/study.yaml`. The
checked-in config explicitly pins `b946d40447b2b597999b9c86d44bee0b452c919f`.
Inference loads the weights and tokenizer at the resolved revision and records it in each row.
[Swiss AI model revision](https://huggingface.co/swiss-ai/Apertus-8B-Instruct-2509/tree/b946d40447b2b597999b9c86d44bee0b452c919f).

## Review scope exception

The owner's PR #62 review explicitly requests the `config/study.yaml` revision pin
as an exception to UC-040's original `touches:` list. This records the existing model
snapshot in the study config, as required by the ticket, without changing it. Staging,
inference and output metadata all use the shared revision resolver.

## Prompt evidence

- `stats_only` uses uncancelled, measured arrivals in the question's segment. It supplies
  their count, mean, median, and linearly interpolated 90th percentile delay in minutes,
  plus the share at or above the configured 3-minute threshold. It also supplies the
  count of known connections and the share with personal slack below zero. Personal slack
  uses the existing margin calculation in [methods §5](methods.md#5-assistant-decision-rule-uc-031).
  Cancelled departures count as missed, and unknown gaps are excluded. An empty
  denominator yields a count of zero and null for the associated statistics.
- `fuzzy_grounded` uses the assistant's decision and explanation sentences with their
  truth and observation counts. It includes the fallback note when the decision uses
  arrival delays. A measured-share explanation can fall between the available quantifiers,
  so the prompt allows an empty claims list when the evidence supports no claim in the
  requested vocabulary.

Both prompts ask for up to three sentences and one JSON entry per quantified claim,
followed by the same answer as plain text. UC-041 parses both representations for audit.

## Run the study

On UBELIX, place the UC-033 question file at `eval/questions.jsonl` and the processed
tables at `data/processed/{arrivals,connections}.parquet`. The runner needs either the
local atlas export at `data/raw/service-points/actual-date-swiss-service-point.csv` or
resolved `connections.hub_stop_ids` in the study config.

From the root of the UBELIX checkout, prepare the Python environment and stage the
model on storage visible to the GPU nodes. The cache holds roughly 16 GB of model files.

```bash
uv sync --locked --extra llm --extra dev
export HF_HOME="$PWD/data/interim/hf-cache"
uv run --locked --extra llm python - <<'PY'
import yaml
from huggingface_hub import snapshot_download

from urban_computing.llm.runner import STUDY_CONFIG, model_revision

settings = yaml.safe_load(STUDY_CONFIG.read_text(encoding="utf-8"))["llm"]
snapshot_download(
    settings["model_id"],
    revision=model_revision(settings),
    allow_patterns=["*.json", "*.jinja", "*.safetensors"],
)
PY
sbatch slurm/run_llm.sbatch
```

The job array uses one RTX 4090 per task, with up to two concurrent tasks. It indexes the
configured product of two conditions, temperatures 0.0 and 0.7, and three seeds. Keep
`uv` on the job's PATH. The prebuilt PyTorch wheel supplies its CUDA libraries, so the
job needs no CUDA or cuDNN module loads. Transformers generates from the cached model
on the allocated GPU with Hugging Face offline mode enabled.
[UBELIX PyTorch setup](https://hpc-unibe-ch.github.io/software/packages/pytorch/).

Submit the same array again to resume. Each task locks its output file and skips
question IDs with complete records. It removes an unterminated final record before
continuing. Use a fresh `--out-dir` for changes to the model revision, questions, dataset,
or prompts.
Temperature 0.0 uses greedy decoding. Temperature 0.7 uses sampling and resets the
configured seed before each question so the result is independent of earlier
completions. Repeatability checks use the same GPU type and software environment.

After the array finishes, run this from the evaluation checkout with SSH access to UBELIX.

```bash
UBELIX_LLM_SOURCE="campus-user@submit02.unibe.ch:/absolute/checkout/data/interim/llm" \
    make llm-collect
```

Collection preserves the directory structure under `data/interim/llm/`.
[UBELIX SSH access](https://hpc-unibe-ch.github.io/firststeps/loggingin/).

## Output and verification

The path is `data/interim/llm/<condition>/<model>/<temperature>/<seed>.jsonl`.
The model directory replaces the slash in the Hugging Face ID with `--`. Each row
contains `question_id`, the run settings and model revision, the SHA-256 `prompt_hash`
of the rendered prompt before the model's chat template, the decoded `raw_output`,
`elapsed_seconds` for generation, and software and GPU versions. The structural
`parse_status` is `json`, `invalid_json`, `free_text`, or `empty`. UC-041 determines
claim validity and handles free-text fallback. Every completion is retained for audit.

To exercise the CLI on CPU, point it at a Question JSONL file.

```bash
uv run --locked python scripts/run_llm.py --mock --questions eval/questions.jsonl
```

Mock mode uses synthetic evidence and writes deterministic output to
`data/interim/llm-mock/` with zero recorded generation time. It uses only the question
file and study config. The offline snapshot and integration tests create the questions
and processed tables they need from synthetic factories.

On a UBELIX GPU allocation with the staged model, run the smoke test to check that two
greedy completions of the same prompt are identical.

```bash
HF_HUB_OFFLINE=1 uv run --locked --offline --extra llm --extra dev \
    pytest -m gpu tests/test_prompts.py
```

**TODO(verify, UC-040)** Record the GPU smoke result and completed Batch C job and row
counts after the real UBELIX run.
