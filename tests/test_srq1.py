"""UC-050: SRQ1 experiments (H1a coverage, H1b stable masking, H1c ranking change)."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml

from tests import factories
from urban_computing.evaluation import srq1
from urban_computing.evaluation.registry import Context
from urban_computing.evaluation.run import verdict
from urban_computing.fuzzy.miner import SummaryRecord

ROOT = Path(__file__).resolve().parents[1]
SPECS = {
    h["id"]: h for h in yaml.safe_load((ROOT / "eval/hypotheses.yaml").read_text())["hypotheses"]
}


def _config():
    return yaml.safe_load((ROOT / "config/study.yaml").read_text(encoding="utf-8"))


def _ctx() -> Context:
    return Context(_config(), False, {"vocabulary": str(ROOT / "config/vocabulary.yaml")}, 1)


def _rec(restriction, truth, coverage, quality, *, half="first", n=100, q="most",
         s="arrival_delay_minutes:on_time", sentence=None) -> SummaryRecord:  # fmt: skip
    return SummaryRecord(
        protoform="simple" if restriction is None else "restricted",
        quantifier=q,
        summarizer=s,
        restriction=restriction,
        segment="network",
        n=n,
        truth=truth,
        coverage=coverage,
        quality=quality,
        half=half,
        sentence=sentence or f"{q} {restriction} {s} {half} {truth}",
    )


def _with_records(records, n_complete=None) -> Context:
    ctx = _ctx()
    ctx.cache["srq1_mined"] = srq1._Mined(
        records, n_complete or {None: 2000, "first": 1000, "second": 1000}
    )
    return ctx


# ------------------------------------------------------------------------------- H1a


def test_h1a_share_counts_only_valid_restricted_summaries_of_the_halves():
    records = [
        _rec("line=S1", 0.9, 0.2, 0.0, n=10),  # valid, low coverage, |R|/n = 1 % < r1
        _rec("line=S2", 0.8, 0.9, 0.72, n=300),  # valid, enough coverage
        _rec("canton=BE", 0.7, 0.4, 0.0, n=50, half="second"),  # valid, low (|R|/n = 5 %)
        _rec("canton=SO", 0.6, 1.0, 0.6, n=500, half="second"),  # v = β exactly: valid
        _rec("line=S3", 0.59, 0.1, 0.0),  # below β: ignored
        _rec("line=S4", 0.9, 0.1, 0.0, half=None),  # whole period: not pooled twice
        _rec(None, 1.0, 1.0, 1.0),  # simple summary: not restricted
        _rec("line=S5", float("nan"), None, None),  # not computable: ignored
    ]
    result = srq1.h1a(_with_records(records))
    assert result.details["n_valid"] == 4
    assert result.details["n_low_coverage"] == 2
    assert result.point == pytest.approx(0.5)
    assert result.ci_low < 0.5 < result.ci_high
    # Breakdown by family and by R's share of the segment (|R|/n vs r1 = 0.02).
    assert result.details["by_family"]["line"]["n_valid"] == 2
    assert result.details["by_family"]["canton"]["n_low_coverage"] == 1
    assert result.details["by_r_share"]["below_r1"] == {
        "n_valid": 1, "n_low_coverage": 1, "point": pytest.approx(1.0),
        "ci_low": pytest.approx(result.details["by_r_share"]["below_r1"]["ci_low"]),
        "ci_high": pytest.approx(1.0),
    }  # fmt: skip
    assert result.details["n_low_coverage_from_small_r"] == 1
    assert result.details["by_r_share"]["at_least_r1"]["n_valid"] == 3
    assert result.details["restriction_families"] == [
        "operator", "product", "line", "canton", "time_band", "weekday_group"
    ]  # fmt: skip


def test_h1a_verdict_rules_follow_the_preregistration():
    many_low = [_rec(f"line=L{i}", 0.9, 0.1, 0.0) for i in range(40)]
    many_ok = [_rec(f"line=M{i}", 0.9, 0.9, 0.81) for i in range(60)]
    result = srq1.h1a(_with_records(many_low + many_ok))
    assert result.point == pytest.approx(0.4)
    assert verdict(SPECS["H1a"], result) == "supported"
    none_low = srq1.h1a(_with_records(many_ok))
    assert none_low.point == 0
    assert verdict(SPECS["H1a"], none_low) == "not_supported"


def test_h1a_without_valid_summaries_has_no_estimate():
    result = srq1.h1a(_with_records([_rec("line=S1", 0.2, 0.1, 0.0)]))
    assert result.point is None
    assert verdict(SPECS["H1a"], result) == "inconclusive"


# ------------------------------------------------------------------------------- H1b


def _arrivals(day, *, local_on_time=20, local_late=20, network=100):
    return pd.concat(
        [
            factories.arrivals([0.0] * network, operating_day=day, every_min=1),
            factories.arrivals(
                [0.0] * local_on_time + [12.0] * local_late,
                operating_day=day,
                every_min=1,
                operator_abbr="BLS",
                product="S",
                line="S23",
                canton="BE",
                journey_id="L",
            ),
        ],
        ignore_index=True,
    )


@pytest.fixture
def masking_ctx(monkeypatch):
    arrivals = pd.concat(
        [_arrivals(date(2026, 10, 5)), _arrivals(date(2026, 10, 20))], ignore_index=True
    )
    assert set(arrivals["half"]) == {"first", "second"}
    monkeypatch.setattr(srq1, "_i4_tables", lambda ctx: (arrivals, None, None))
    return _ctx()


def test_h1b_counts_cases_stable_in_both_halves_with_sentence_pairs(masking_ctx):
    # Network: 120 of 140 on time (most), 20 of 140 very late (few). The BLS line S23 in
    # canton BE (40 rows) is half on time, half very late: "about half" for both words. The
    # same rows form operator=BLS, line=S23 and canton=BE: 3 restrictions x 2 summarizers.
    result = srq1.h1b(masking_ctx)
    assert result.value == 6
    assert verdict(SPECS["H1b"], result) == "supported"
    assert result.details["by_family"] == {"operator": 2, "line": 2, "canton": 2}
    cases = {(c["restriction"], c["summarizer"]): c for c in result.details["examples"]}
    on_time = cases[("line=S23", "arrival_delay_minutes:on_time")]
    assert on_time["network_quantifier_first"] == on_time["network_quantifier_second"] == "most"
    assert on_time["local_quantifier_first"] == on_time["local_quantifier_second"] == "about_half"
    assert on_time["network_sentence"].startswith("Most of the arrivals")
    assert on_time["local_sentence"].startswith("About half of the S23 arrivals")
    very_late = cases[("canton=BE", "arrival_delay_minutes:very_late")]
    assert (very_late["network_quantifier_first"], very_late["local_quantifier_first"]) == (
        "few",
        "about_half",
    )


def test_h1b_needs_the_case_in_both_halves(monkeypatch):
    # Second half: S23 behaves like the network (all on time), so no case is stable.
    arrivals = pd.concat(
        [
            _arrivals(date(2026, 10, 5)),
            _arrivals(date(2026, 10, 20), local_on_time=40, local_late=0),
        ],
        ignore_index=True,
    )
    monkeypatch.setattr(srq1, "_i4_tables", lambda ctx: (arrivals, None, None))
    result = srq1.h1b(_ctx())
    assert result.value == 0
    assert verdict(SPECS["H1b"], result) == "not_supported"


def test_masking_table_lists_every_case(masking_ctx):
    table = srq1.masking_table(masking_ctx)
    assert table.name == "srq1_masking_cases"
    assert len(table.rows) == 6
    assert {row["family"] for row in table.rows} == {"operator", "line", "canton"}


# ------------------------------------------------------------------------------- H1c


def _whole(i, truth, quality, n=100):
    return _rec(f"line=L{i:02d}", truth, 1.0, quality, half=None, n=n, sentence=f"s{i:02d}")


def test_h1c_identical_rankings_give_tau_one():
    records = [_whole(i, 1 - i / 100, 1 - i / 100) for i in range(25)]
    result = srq1.h1c(_with_records(records))
    assert result.details["n_top"] == 20
    assert result.point == pytest.approx(1.0)
    assert verdict(SPECS["H1c"], result) == "not_supported"
    # Only the 20 highest truths are used.
    assert [row["sentence"] for row in result.details["top20"]][-1] == "s19"


def test_h1c_reversed_rankings_support_the_hypothesis():
    records = [_whole(i, 1 - i / 100, i / 100) for i in range(20)]
    result = srq1.h1c(_with_records(records))
    assert result.point == pytest.approx(-1.0)
    assert 0 <= result.p <= 1
    assert verdict(SPECS["H1c"], result) == "supported"


def test_h1c_reports_large_restrictions_separately():
    # Ten small restrictions (|R|/n = 1 %) rank top by v but have Q_c = 0.
    small = [_whole(i, 1 - i / 1000, 0.0, n=10) for i in range(10)]
    large = [_whole(10 + i, 0.9 - i / 100, 0.9 - i / 100, n=500) for i in range(20)]
    result = srq1.h1c(_with_records(small + large))
    assert result.details["large_r"]["n"] == 20
    assert result.details["large_r"]["tau"] == pytest.approx(1.0)
    assert result.point < 0.8


def test_h1c_constant_ranking_is_reported_not_guessed():
    records = [_whole(i, 1.0, 0.5) for i in range(20)]
    result = srq1.h1c(_with_records(records))
    assert result.point is None
    assert result.details["reason"] == "constant_ranking"
    assert verdict(SPECS["H1c"], result) == "inconclusive"


def test_coverage_table_and_figure(tmp_path):
    records = [
        _rec("line=S1", 0.9, 0.2, 0.0, n=10),
        _rec("canton=BE", 0.9, 0.9, 0.81, n=300, half="second"),
    ]
    ctx = _with_records(records)
    ctx.paths["results_dir"] = str(tmp_path)
    table = srq1.coverage_table(ctx)
    groups = {row["group"]: row for row in table.rows}
    assert groups["all"]["n_valid"] == 2
    assert groups["family=line"]["point"] == pytest.approx(1.0)
    assert groups["r_share=below_r1"]["n_low_coverage"] == 1
    assert (tmp_path / "figures" / "srq1_coverage.png").stat().st_size > 0
