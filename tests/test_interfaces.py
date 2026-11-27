"""Interface contract: function names, parameters and data contracts that tickets build on.

If this test fails, someone changed a frozen interface. That needs a decision entry
(docs/decisions.md) and an update here in the same PR, because other agents are coding
against these signatures in parallel.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

from tests import factories
from urban_computing.data import schemas

INTERFACE = {
    "urban_computing.data.synthetic": {"generate": ["out_dir", "seed", "separator"]},
    "urban_computing.data.download": {
        "download_ist_daten": ["start", "end", "raw_dir", "dry_run"],
        "download_service_points": ["raw_dir", "dry_run"],
        "write_manifest": ["files", "manifest_path"],
        "verify_manifest": ["manifest_path"],
    },
    "urban_computing.data.ingest": {
        "ingest_day": ["csv_path", "out_dir"],
        "ingest_all": ["raw_dir", "out_dir"],
    },
    "urban_computing.data.quality": {
        "build_quality_report": ["interim_dir", "config_path", "out_md", "out_json"]
    },
    "urban_computing.data.arrivals": {
        "build_arrivals": ["stop_events", "service_points", "config"],
        "build_arrivals_file": ["interim_dir", "service_points_path", "config_path", "out_path"],
    },
    "urban_computing.data.connections": {
        "build_connections": ["stop_events", "hub_stop_ids", "config"],
        "build_connections_file": [
            "interim_dir",
            "service_points_path",
            "config_path",
            "out_path",
        ],
    },
    "urban_computing.fuzzy.vocabulary": {"load_vocabulary": ["path"]},
    "urban_computing.fuzzy.truth": {
        "fuzzy_proportion": ["mu_S", "mu_R", "tnorm"],
        "truth_simple": ["mu_S", "Q"],
        "truth_restricted": ["mu_R", "mu_S", "Q", "tnorm"],
    },
    "urban_computing.fuzzy.quality": {
        "coverage": ["mu_R", "mu_S", "params"],
        "quality_qc": ["truth", "cov", "tnorm", "c_min"],
        "regional_quality": ["per_region_truth", "region_sizes"],  # D-027 (UC-022)
    },
    "urban_computing.fuzzy.miner": {
        "mine": [
            "values",
            "restrictions",
            "vocab",
            "beta",
            "segment",
            "half",
            "quantifier_set",
            "tnorm",
        ]
    },
    "urban_computing.assistant.engine": {
        "answer": ["question", "connections", "arrivals", "vocab", "config"],
        "verify_answer": ["ans", "connections", "arrivals", "vocab", "config", "tol"],
    },
    "urban_computing.assistant.crisp": {"crisp_answer": ["question", "arrivals", "config"]},
    "urban_computing.assistant.render": {
        "truth_badge": ["truth"],
        "answer_view_model": ["ans"],
    },
    "urban_computing.llm.prompts": {"render_prompt": ["condition", "question", "stats", "answer"]},
    "urban_computing.llm.runner": {
        "run": ["questions_path", "condition", "model_id", "temperature", "seed", "out_dir", "mock"]
    },
    "urban_computing.llm.parser": {"parse_output": ["question_id", "raw", "lexicon"]},
    "urban_computing.llm.checkers": {"check": ["claim", "values", "vocab", "config"]},
    "urban_computing.evaluation.stats": {
        "wilson_ci": ["successes", "n", "alpha"],
        "mcnemar": ["b", "c"],
        "wilcoxon_paired": ["x", "y"],
        "kendall_tau_perm": ["a", "b", "n_perm", "seed"],
        "fisher_exact": ["table"],
        "bootstrap_ci": ["values", "stat", "n_resamples", "seed", "alpha"],
    },
    "urban_computing.evaluation.segments": {"restriction_masks": ["arrivals", "families", "min_n"]},
    "urban_computing.evaluation.questions": {
        "make_questions": ["connections", "config", "seed"],
        "write_questions": ["questions", "path"],
    },
    "urban_computing.evaluation.registry": {
        "experiment": ["hypothesis_id"],
        "invariant": ["invariant_id"],
        "table": ["name"],
    },
}


@pytest.mark.parametrize("module_name", sorted(INTERFACE))
def test_module_exposes_frozen_signatures(module_name):
    mod = importlib.import_module(module_name)
    for fn_name, params in INTERFACE[module_name].items():
        fn = getattr(mod, fn_name, None)
        assert callable(fn), f"{module_name}.{fn_name} missing"
        actual = list(inspect.signature(fn).parameters)
        assert actual[: len(params)] == params, f"{module_name}.{fn_name}: {actual} != {params}"


def test_contract_models_fields():
    from urban_computing.assistant.contract import Answer, Explanation, Question
    from urban_computing.fuzzy.miner import SummaryRecord
    from urban_computing.llm.parser import Claim

    assert {"hub", "time_band", "weekday_group", "margin_min"} <= set(Question.model_fields)
    assert {"sentence", "quantifier", "summarizer", "truth", "n"} <= set(Explanation.model_fields)
    assert {"question", "decision", "explanations", "crisp_decision", "provenance"} <= set(
        Answer.model_fields
    )
    assert {"question_id", "slot", "quantifier", "summarizer", "status"} <= set(Claim.model_fields)
    assert {"truth", "coverage", "quality", "sentence", "n"} <= set(
        SummaryRecord.__dataclass_fields__
    )


def test_factories_follow_schemas():
    factories.assert_schema(factories.arrivals([0.5, 2.0, None, 7.0]), schemas.ARRIVALS)
    factories.assert_schema(factories.connections([5.0, 1.0, None]), schemas.CONNECTIONS)
    ev = factories.stop_events(
        [
            {
                "planned_arrival": factories.ts(factories.DEFAULT_DAY, "07:00"),
                "actual_arrival": factories.ts(factories.DEFAULT_DAY, "07:02", 30),
            }
        ]
    )
    factories.assert_schema(ev, schemas.STOP_EVENTS)


def test_sample_answer_roundtrip():
    from urban_computing.assistant.contract import Answer

    ans = factories.sample_answer()
    assert Answer.model_validate_json(ans.model_dump_json()) == ans


def test_registry_rejects_duplicates():
    from urban_computing.evaluation import registry

    @registry.experiment("HX_test")
    def f(ctx):  # pragma: no cover - registration only
        return registry.Result(point=0.0)

    with pytest.raises(ValueError):

        @registry.experiment("HX_test")
        def g(ctx):  # pragma: no cover
            return registry.Result(point=0.0)

    registry.EXPERIMENTS.pop("HX_test")
