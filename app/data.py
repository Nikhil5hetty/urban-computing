"""Data loading for the prototype (UC-060): processed tables, or the fixture with --sample.

No LLM is called: the "Chatbot view" only reads cached outputs from data/interim/llm/
(UC-040) for questions of the evaluation set (eval/questions.jsonl, UC-033).
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from urban_computing.assistant.contract import Question
from urban_computing.evaluation import registry
from urban_computing.evaluation.invariants import _i4_tables
from urban_computing.fuzzy.vocabulary import Vocabulary, load_vocabulary

ROOT = Path(__file__).resolve().parents[1]
RAW_KEYS = ("raw_output", "raw", "output", "text")  # TODO(verify): UC-040 record field name


@dataclass
class AppData:
    config: dict
    vocab: Vocabulary
    arrivals: pd.DataFrame
    connections: pd.DataFrame
    sample: bool
    tmp: Any = field(default=None, repr=False)  # keeps the sample's temp dir alive


def load(sample: bool, root: Path = ROOT) -> AppData:
    """Study config, vocabulary and tables. `sample`: build arrivals / connections from the
    synthetic fixture (tests/fixtures/ist_sample), exactly like invariant I4."""
    config = yaml.safe_load((root / "config" / "study.yaml").read_text(encoding="utf-8"))
    vocab_path = root / "config" / "vocabulary.yaml"
    tmp = None
    if sample:
        tmp = tempfile.TemporaryDirectory(prefix="uc-app-")
        base = Path(tmp.name)
        (base / "interim").mkdir()
        (base / "processed").mkdir()
        fixtures = root / "tests" / "fixtures" / "ist_sample"
        paths = {"raw_dir": str(fixtures), "service_points_dir": str(fixtures),
                 "interim_dir": str(base / "interim"), "processed_dir": str(base / "processed"),
                 "arrivals": str(base / "processed" / "arrivals.parquet"),
                 "connections": str(base / "processed" / "connections.parquet"),
                 "vocabulary": str(vocab_path)}  # fmt: skip
    else:
        data = config["data"]
        processed = root / data["processed_dir"]
        paths = {"raw_dir": str(root / data["raw_dir"]),
                 "service_points_dir": str(root / data["service_points_dir"]),
                 "interim_dir": str(root / data["interim_dir"]), "processed_dir": str(processed),
                 "arrivals": str(processed / "arrivals.parquet"),
                 "connections": str(processed / "connections.parquet"),
                 "vocabulary": str(vocab_path)}  # fmt: skip
    ctx = registry.Context(config=config, sample=sample, paths=paths, seed=config["study"]["seed"])
    arrivals, connections, hub_ids = _i4_tables(ctx)
    if hub_ids:
        config = {**config, "connections": {**config["connections"], "hub_stop_ids": hub_ids}}
    return AppData(config, load_vocabulary(vocab_path), arrivals, connections, sample, tmp)


def lines_at(data: AppData, hub: str, column: str = "arr_line") -> list[str]:
    """Lines observed at the hub in the connections table (sorted), for the dropdowns."""
    c = data.connections
    values = c.loc[c["hub"] == hub, column].dropna().astype(str)
    return sorted(v for v in values.unique() if v)


def cached_llm_answer(question: Question, root: Path = ROOT) -> tuple[str, str] | None:
    """(question_id, raw LLM output) cached for this question, or None.

    Looks the question up in eval/questions.jsonl (same fields except the id) and then in
    data/interim/llm/fuzzy_grounded/**/*.jsonl (temperature 0 first). Never calls an LLM.
    """
    qfile = root / "eval" / "questions.jsonl"
    llm_dir = root / "data" / "interim" / "llm" / "fuzzy_grounded"
    if not qfile.exists() or not llm_dir.exists():
        return None
    want = question.model_dump(exclude={"question_id"})
    qid = None
    for line in qfile.read_text(encoding="utf-8").splitlines():
        if line.strip():
            q = Question.model_validate_json(line)
            if q.model_dump(exclude={"question_id"}) == want:
                qid = q.question_id
                break
    if qid is None:
        return None
    for path in sorted(llm_dir.rglob("*.jsonl"), key=lambda p: ("/0.0/" not in str(p), str(p))):
        for line in path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line) if line.strip() else {}
            if rec.get("question_id") == qid:
                raw = next((rec[k] for k in RAW_KEYS if isinstance(rec.get(k), str)), None)
                if raw is not None:
                    return qid, raw
    return None
