"""Run local Apertus inference and checkpoint one JSONL record per question."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import platform
import re
from collections.abc import Callable
from functools import partial
from importlib import metadata
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, BinaryIO

import yaml

from urban_computing.assistant.contract import (
    STUDY_CONFIG,
    Answer,
    Explanation,
    Provenance,
    Question,
)
from urban_computing.llm.parser import _find_json
from urban_computing.llm.prompts import STUDY_CONDITIONS, render_prompt

if TYPE_CHECKING:
    import pandas as pd

APERTUS_MODEL_ID = "swiss-ai/Apertus-8B-Instruct-2509"
APERTUS_REVISION = "b946d40447b2b597999b9c86d44bee0b452c919f"
_MOCK_TEXT = "Few connections are missed."


def model_revision(settings: dict) -> str:
    """Resolve the full Hugging Face commit hash from the study's `llm` settings."""
    model_id = settings["model_id"]
    fallback = APERTUS_REVISION if model_id == APERTUS_MODEL_ID else None
    revision = settings.get("model_revision", fallback)
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError(f"llm.model_revision must be a full commit hash for {model_id!r}")
    return revision


def _read_questions(questions_path: Path, config: dict) -> dict[str, Question]:
    questions = {}
    with questions_path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            question = Question.model_validate_json(line, context={"study_config": config})
            question_id = question.question_id
            if not question_id or not question_id.strip() or question_id in questions:
                raise ValueError(
                    f"{questions_path}:{line_number}: missing or duplicate question_id"
                )
            questions[question_id] = question
    return questions


def _stats(
    question: Question, arrivals: pd.DataFrame, pairs: pd.DataFrame, config: dict
) -> dict[str, float | int | None]:
    import numpy as np

    from urban_computing.assistant.crisp import _segment
    from urban_computing.assistant.engine import connection_segment, personal_slack

    arrivals, _ = _segment(question, arrivals, config)
    delay = arrivals["delay_min"]
    punctual_threshold = float(config["crisp_baseline"]["punctual_threshold_minutes"])
    slack = personal_slack(
        connection_segment(question, pairs),
        question.margin_min,
        float(config["connections"]["min_transfer_minutes_default"]),
    )
    known_slack = slack[~np.isnan(slack)]
    return {
        "n": len(delay),
        "mean_delay_min": float(delay.mean()) if len(delay) else None,
        "median_delay_min": float(delay.median()) if len(delay) else None,
        "p90_delay_min": float(delay.quantile(0.9)) if len(delay) else None,
        "punctual_threshold_min": punctual_threshold,
        "share_at_or_above_threshold": (
            float((delay >= punctual_threshold).mean()) if len(delay) else None
        ),
        "n_connections": len(known_slack),
        "share_missed": float((known_slack < 0).mean()) if len(known_slack) else None,
    }


def _mock_prompt(question: Question, *, condition: str, config: dict) -> str:
    if condition == "stats_only":
        return render_prompt(
            condition,
            question,
            stats={
                "n": 1,
                "mean_delay_min": 0.0,
                "median_delay_min": 0.0,
                "p90_delay_min": 0.0,
                "punctual_threshold_min": config["crisp_baseline"]["punctual_threshold_minutes"],
                "share_at_or_above_threshold": 0.0,
                "n_connections": 1,
                "share_missed": 0.0,
            },
        )
    answer = Answer(
        question=question,
        decision="safe",
        explanations=[
            Explanation(
                sentence=_MOCK_TEXT,
                quantifier="few",
                summarizer="connection_slack_minutes:missed",
                truth=1.0,
                n=1,
            )
        ],
        provenance=Provenance(period="synthetic", config_hash="mock"),
    )
    return render_prompt(condition, question, answer=answer)


def _prompt_renderer(condition: str, config: dict) -> Callable[[Question], str]:
    import pandas as pd

    from urban_computing.assistant import engine
    from urban_computing.data.connections import _hub_ids
    from urban_computing.fuzzy.vocabulary import load_vocabulary

    data = config["data"]
    processed = Path(data["processed_dir"])
    arrivals = pd.read_parquet(processed / "arrivals.parquet")
    pairs = pd.read_parquet(processed / "connections.parquet")
    settings = config["connections"]
    if not settings.get("hub_stop_ids"):
        atlas = Path(data["service_points_dir"]) / "actual-date-swiss-service-point.csv"
        settings["hub_stop_ids"] = _hub_ids(atlas, settings["hubs"])

    if condition == "stats_only":
        return lambda question: render_prompt(
            condition, question, stats=_stats(question, arrivals, pairs, config)
        )
    vocab = load_vocabulary(engine.VOCAB_PATH)
    return lambda question: render_prompt(
        condition, question, answer=engine.answer(question, pairs, arrivals, vocab, config)
    )


def _model_generator(
    model_id: str, revision: str, temperature: float, seed: int, max_new_tokens: int
) -> tuple[Callable[[str], str], dict[str, str]]:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

    import torch
    import transformers

    if not torch.cuda.is_available():
        raise RuntimeError("Apertus requires a CUDA GPU. Use --mock for offline CPU runs.")
    torch.use_deterministic_algorithms(True)

    load_options = {"revision": revision, "local_files_only": True}
    tokenizer = transformers.AutoTokenizer.from_pretrained(model_id, **load_options)
    model = transformers.AutoModelForCausalLM.from_pretrained(
        model_id,
        dtype=torch.bfloat16,
        device_map={"": "cuda:0"},
        attn_implementation="eager",
        **load_options,
    )
    model.eval()
    generation_options = {"do_sample": temperature > 0, "max_new_tokens": max_new_tokens}
    if temperature > 0:
        generation_options["temperature"] = temperature

    def generate(prompt: str) -> str:
        # Reset the RNG before each question so resuming does not change sampled answers.
        transformers.set_seed(seed)
        tokens = tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        ).to(model.device)
        with torch.inference_mode():
            output = model.generate(**tokens, **generation_options)
        return tokenizer.decode(
            output[0, tokens["input_ids"].shape[-1] :], skip_special_tokens=True
        )

    return generate, {
        "torch": str(torch.__version__),
        "transformers": transformers.__version__,
        "accelerate": metadata.version("accelerate"),
        "cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0),
    }


def _mock_generate(_prompt: str) -> str:
    claim = {"quantifier": "few", "summarizer": "missed", "restriction": None}
    return json.dumps({"claims": [claim], "text": _MOCK_TEXT}) + "\n" + _MOCK_TEXT


def _parse_status(raw: str) -> str:
    obj, _ = _find_json(raw)
    if obj is None:
        if not raw.strip():
            return "empty"
        return "invalid_json" if "{" in raw else "free_text"
    claims = obj["claims"]
    if not isinstance(obj.get("text"), str) or not isinstance(claims, list):
        return "invalid_json"
    valid = all(
        isinstance(claim, dict)
        and isinstance(claim.get("quantifier"), str)
        and isinstance(claim.get("summarizer"), str)
        and "restriction" in claim
        and (claim["restriction"] is None or isinstance(claim["restriction"], str))
        for claim in claims
    )
    return "json" if valid else "invalid_json"


def _completed(stream: BinaryIO, settings: dict) -> set[str]:
    finished = set()
    offset = 0
    for line in stream:
        if not line.endswith(b"\n"):
            # An interrupted write can only leave an incomplete final line.
            stream.truncate(offset)
            break
        row = json.loads(line)
        if any(row.get(key) != value for key, value in settings.items()):
            raise ValueError(
                f"{stream.name}: existing output was generated with different settings"
            )
        question_id = row["question_id"]
        if question_id in finished:
            raise ValueError(f"{stream.name}: duplicate output for {question_id!r}")
        finished.add(question_id)
        offset += len(line)
    return finished


def run(
    questions_path: Path,
    condition: str,
    model_id: str,
    temperature: float,
    seed: int,
    out_dir: Path,
    mock: bool = False,
) -> Path:
    """Generate resumable JSONL for a Question file and one condition, model, temperature and seed.

    Write raw completions and generation time in seconds under `out_dir`. Mock runs use
    synthetic evidence and fixed text without loading Parquet or any inference libraries.
    """
    if condition not in STUDY_CONDITIONS:
        raise ValueError(f"Unsupported runner condition: {condition!r}")
    if not re.fullmatch(r"[A-Za-z0-9][\w.-]*(?:/[A-Za-z0-9][\w.-]*)?", model_id):
        raise ValueError(f"Invalid model ID: {model_id!r}")
    if not math.isfinite(temperature) or temperature < 0:
        raise ValueError("Temperature must be finite and nonnegative")
    config = yaml.safe_load(STUDY_CONFIG.read_text(encoding="utf-8"))
    llm = config["llm"]
    revision = model_revision(llm) if model_id == llm["model_id"] else None
    if not mock and revision is None:
        raise ValueError(f"No pinned revision for {model_id!r}")

    questions = _read_questions(questions_path, config)
    max_new_tokens = int(llm["max_new_tokens"])
    temperature = float(temperature)
    path = out_dir / condition / model_id.replace("/", "--") / str(temperature) / f"{seed}.jsonl"
    settings = {
        "condition": condition,
        "model_id": model_id,
        "model_revision": revision,
        "temperature": temperature,
        "seed": seed,
        "max_new_tokens": max_new_tokens,
        "mock": mock,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        finished = _completed(stream, settings)
        pending = [(qid, question) for qid, question in questions.items() if qid not in finished]
        if not pending:
            return path

        versions = {"python": platform.python_version(), "pydantic": metadata.version("pydantic")}
        if mock:
            render = partial(_mock_prompt, condition=condition, config=config)
            generate = _mock_generate
        else:
            assert revision is not None
            render = _prompt_renderer(condition, config)
            generate, backend = _model_generator(
                model_id, revision, temperature, seed, max_new_tokens
            )
            versions.update(
                {name: metadata.version(name) for name in ("numpy", "pandas", "pyarrow")}
            )
            versions.update(backend)

        stream.seek(0, os.SEEK_END)
        for question_id, question in pending:
            prompt = render(question)
            started = perf_counter()
            raw = generate(prompt)
            elapsed = 0.0 if mock else perf_counter() - started
            record = {
                **settings,
                "question_id": question_id,
                "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "raw_output": raw,
                "parse_status": _parse_status(raw),
                "elapsed_seconds": elapsed,
                "versions": versions,
            }
            stream.write((json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
    return path
