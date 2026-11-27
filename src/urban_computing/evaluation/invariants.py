"""Invariant providers loaded by the project evaluation runner."""

from pathlib import Path

import duckdb

from urban_computing.data.ingest import ingest_all
from urban_computing.data.quality import _open_events, _punctuality
from urban_computing.evaluation import registry


@registry.invariant("I5")
def punctual_arrival_sanity(ctx: registry.Context) -> registry.InvariantResult:
    """Check the preregistered band for the share of punctual REAL train arrivals."""
    interim = Path(ctx.paths["interim_dir"])
    if ctx.sample:
        ingest_all(Path(ctx.paths["raw_dir"]), interim / "ist")
    with duckdb.connect() as connection:
        try:
            _open_events(connection, interim)
        except FileNotFoundError as error:
            return registry.InvariantResult(False, {"reason": str(error)})
        i5, _ = _punctuality(connection, ctx.config)
    return registry.InvariantResult(i5["pass"], i5)


# ---------------------------------------------------------------------------- I4 (UC-031)

# Hub identifiers documented in docs/data.md §6 (UC-014); used only to build the synthetic
# fixture's atlas in sample mode. Real runs resolve ids from the atlas export.
SAMPLE_HUB_IDS = {
    "Zürich HB": ("8503000", "ch:1:sloid:3000", "ZH"),
    "Bern": ("8507000", "ch:1:sloid:7000", "BE"),
    "Olten": ("8500218", "ch:1:sloid:218", "SO"),
}
I4_MAX_QUESTIONS = 300


def _i4_tables(ctx: registry.Context):
    """(arrivals, connections, hub_stop_ids) for I4; built from the fixture in sample mode."""
    import pandas as pd

    from urban_computing.data.arrivals import build_arrivals_file
    from urban_computing.data.connections import _hub_ids, build_connections_file

    if "i4_tables" in ctx.cache:
        return ctx.cache["i4_tables"]
    interim, processed = Path(ctx.paths["interim_dir"]), Path(ctx.paths["processed_dir"])
    arr_path, con_path = Path(ctx.paths["arrivals"]), Path(ctx.paths["connections"])
    if ctx.sample:
        if not any((interim / "ist").glob("*.parquet")):
            ingest_all(Path(ctx.paths["raw_dir"]), interim / "ist")
        atlas = processed / "sample_atlas.csv"
        atlas.write_text(
            "designationOfficial;isoCountryCode;number;sloid;cantonAbbreviation\n"
            + "".join(f"{h};CH;{n};{s};{c}\n" for h, (n, s, c) in SAMPLE_HUB_IDS.items()),
            encoding="utf-8",
        )
        config_path = processed / "sample_study.yaml"
        import yaml

        config_path.write_text(yaml.safe_dump(ctx.config, allow_unicode=True), encoding="utf-8")
        build_arrivals_file(interim, atlas, config_path, arr_path)
        build_connections_file(interim, atlas, config_path, con_path)
    else:
        atlas = Path(ctx.paths["service_points_dir"]) / "actual-date-swiss-service-point.csv"
    hub_ids = _hub_ids(atlas, ctx.config["connections"]["hubs"]) if atlas.exists() else None
    tables = (pd.read_parquet(arr_path), pd.read_parquet(con_path), hub_ids)
    ctx.cache["i4_tables"] = tables
    return tables


def _i4_questions(connections, config: dict) -> list:
    """eval/questions.jsonl (UC-033) if present, else one question per observed
    (hub, arriving line, time band) x passenger margin, capped at I4_MAX_QUESTIONS."""
    from urban_computing.assistant.contract import Question

    qfile = Path(config["evaluation"].get("questions_file", "eval/questions.jsonl"))
    if qfile.exists():
        lines = qfile.read_text(encoding="utf-8").splitlines()
        return [Question.model_validate_json(x) for x in lines if x.strip()][:I4_MAX_QUESTIONS]
    cells = (
        connections.dropna(subset=["arr_line"])[["hub", "arr_line", "time_band"]]
        .drop_duplicates()
        .sort_values(["hub", "arr_line", "time_band"])
    )
    out = []
    for hub, line, band in cells.itertuples(index=False):
        for m in config["connections"]["user_margins_minutes"]:
            out.append(Question(hub=hub, arr_line=line, time_band=band, weekday_group="all",
                                margin_min=float(m)))  # fmt: skip
    return out[:I4_MAX_QUESTIONS]


@registry.invariant("I4")
def faithful_explanations(ctx: registry.Context) -> registry.InvariantResult:
    """I4: 100% of explanation sentences recompute to their stated truth (UC-031)."""
    from urban_computing.assistant.engine import NoDataError, answer, verify_answer
    from urban_computing.fuzzy.vocabulary import load_vocabulary

    try:
        arrivals, connections, hub_ids = _i4_tables(ctx)
    except FileNotFoundError as error:
        return registry.InvariantResult(False, {"reason": str(error)})
    config = {**ctx.config, "connections": {**ctx.config["connections"]}}
    if hub_ids:
        config["connections"]["hub_stop_ids"] = hub_ids
    vocab = load_vocabulary(Path(ctx.paths.get("vocabulary", "config/vocabulary.yaml")))
    answered, failed, sentences, gap = 0, [], 0, 0
    for q in _i4_questions(connections, config):
        try:
            ans = answer(q, connections, arrivals, vocab, config)
        except NoDataError:
            continue
        answered += 1
        sentences += len(ans.explanations)
        gap += any(e.quantifier == "count" for e in ans.explanations)
        if not verify_answer(ans, connections, arrivals, vocab, config):
            failed.append(q.model_dump())
    # answers whose p_miss falls where no core quantifier reaches beta (measured-share
    # sentence instead; a CWW finding for the discussion, PM review of #56)
    details = {"answers": answered, "explanation_sentences": sentences, "failed": failed[:20],
               "n_failed": len(failed), "vocabulary_gap_answers": gap}  # fmt: skip
    return registry.InvariantResult(answered > 0 and not failed, details)
