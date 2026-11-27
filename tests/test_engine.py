"""UC-031: perception-aware decision with faithful explanation (I4), on synthetic data."""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from tests import factories
from urban_computing.assistant.engine import (
    FALLBACK_MIN_CONNECTIONS,
    OWN_ARRIVALS,
    OWN_CONNECTIONS,
    NoDataError,
    answer,
    decide,
    decision_sets,
    personal_slack,
    verify_answer,
)
from urban_computing.evaluation import registry
from urban_computing.fuzzy.vocabulary import load_vocabulary

ROOT = Path(__file__).resolve().parents[1]
VOCAB = load_vocabulary(ROOT / "config" / "vocabulary.yaml")
CONFIG = yaml.safe_load((ROOT / "config" / "study.yaml").read_text())
BETA = CONFIG["mining"]["beta"]
CAUTION = {"safe": 0, "at_risk": 1, "risky": 2}
Q = factories.sample_question  # Olten, IC1 -> IR16, morning_peak, monday, margin 4


def conns(gaps, planned=4.0, **kw) -> pd.DataFrame:
    return factories.connections(gaps, planned_gap_min=planned, **kw)


def arrs(delays, **kw) -> pd.DataFrame:
    return factories.arrivals(delays, **kw)


# --------------------------------------------------------------------- decision rule


@pytest.mark.parametrize(
    "p,word",
    [(0.0, "safe"), (0.05, "safe"), (0.074, "safe"), (0.075, "at_risk"), (0.15, "at_risk"),
     (0.249, "at_risk"), (0.25, "risky"), (0.3, "risky"), (1.0, "risky")],
)  # fmt: skip
def test_decision_words_and_cautious_ties(p, word):
    # 0.075 and 0.25 are crossovers (mu = 0.5 for both words): ties go to the cautious word,
    # which matches the crisp baseline's thresholds (D-026)
    assert decide(p, decision_sets(CONFIG)) == word


def test_decision_sets_from_vocabulary_yaml_and_config_override():
    sets = decision_sets(CONFIG)
    assert set(sets) == {"safe", "at_risk", "risky"}
    raw = yaml.safe_load((ROOT / "config" / "vocabulary.yaml").read_text())["decision_sets"]
    assert raw["at_risk"] == [0.05, 0.10, 0.20, 0.30]
    t = CONFIG["crisp_baseline"]["decision_thresholds"]
    for p in (t["at_risk"], t["risky"]):  # crisp thresholds = fuzzy crossovers
        mus = sorted(float(fn(np.asarray(p))) for fn in sets.values())
        assert mus[-1] == pytest.approx(0.5) and mus[-2] == pytest.approx(0.5)
    cfg = {**CONFIG, "decision_sets": {"safe": [None, None, 0.5, 0.6],
           "at_risk": [0.5, 0.6, 0.7, 0.8], "risky": [0.7, 0.8, None, None]}}  # fmt: skip
    assert decide(0.3, decision_sets(cfg)) == "safe"


# --------------------------------------------------------------------- encoder


def test_personal_slack_uses_margin_and_cancellations():
    seg = conns([4.0, 1.0, None, 6.0])  # planned 4: delays shift by 0, -3, cancelled, +2
    s = personal_slack(seg, margin_min=3.0, min_transfer_min=2.0)
    np.testing.assert_array_equal(s, [1.0, -2.0, -np.inf, 3.0])


def test_cancellations_count_as_missed_and_raise_p_miss():
    ok = [4.0] * 30  # slack 4 + 0 - 2 = 2: comfortable, never missed
    base = answer(Q(), conns(ok), arrs([0.0] * 10), VOCAB, CONFIG)
    with_cancel = answer(Q(), conns(ok + [None] * 10), arrs([0.0] * 10), VOCAB, CONFIG)
    assert base.p_miss == 0.0 and base.decision == "safe"
    assert with_cancel.p_miss == pytest.approx(10 / 40)  # cancelled B = slack -inf = missed
    assert with_cancel.decision == "risky"
    unknown = conns(ok)
    unknown = pd.concat([unknown, conns([4.0] * 10).assign(actual_gap_min=np.nan)],
                        ignore_index=True)  # fmt: skip
    assert answer(Q(), unknown, arrs([0.0]), VOCAB, CONFIG).p_miss == 0.0  # NaN gap: dropped


def test_margin_matters():
    # 13 of 25 connections lose 3 minutes (actual gap 1 of planned 4), 12 are on time
    data = conns([1.0] * 13 + [4.0] * 12)
    tight = answer(Q(margin_min=3), data, arrs([0.0]), VOCAB, CONFIG)
    loose = answer(Q(margin_min=10), data, arrs([0.0]), VOCAB, CONFIG)
    assert tight.p_miss == pytest.approx(0.52) and tight.decision == "risky"
    assert loose.p_miss == 0.0 and loose.decision == "safe"


def test_decision_is_monotone_in_delays():
    rng = np.random.default_rng(CONFIG["study"]["seed"])
    for _ in range(30):
        gaps = rng.uniform(0.5, 8.0, 40)
        last = -1
        for extra in np.linspace(0, 6, 13):  # every arrival gets later
            a = answer(Q(), conns(list(gaps - extra)), arrs([0.0]), VOCAB, CONFIG)
            assert CAUTION[a.decision] >= last
            last = CAUTION[a.decision]
        last = -1
        for extra in np.linspace(0, 8, 9):  # fallback path: arrival delays grow
            a = answer(Q(), conns([4.0] * 3), arrs(list(rng.uniform(0, 3, 30) + extra)),
                       VOCAB, CONFIG)  # fmt: skip
            assert a.provenance.fallback and CAUTION[a.decision] >= last
            last = CAUTION[a.decision]


# --------------------------------------------------------------------- fallback


def test_small_n_falls_back_to_arrivals_with_margin():
    few = conns([4.0] * (FALLBACK_MIN_CONNECTIONS - 1))
    delays = [5.0] * 6 + [0.0] * 34  # 15 % at least 4 min late -> late for a 4-min margin
    a = answer(Q(), few, arrs(delays), VOCAB, CONFIG)
    assert a.provenance.fallback and a.p_miss == pytest.approx(0.15)
    assert a.decision == "at_risk"
    assert "too few matching connections" in a.to_text()
    own = [e for e in a.explanations if e.restriction == OWN_ARRIVALS]
    assert own and own[0].summarizer == "arrival_delay_minutes:late_for_my_transfer"
    assert answer(Q(), conns([4.0] * 20), arrs(delays), VOCAB, CONFIG).provenance.fallback is False


def test_no_data_raises():
    with pytest.raises(NoDataError):
        answer(Q(), conns([4.0] * 3), arrs([None] * 5), VOCAB, CONFIG)


# --------------------------------------------------------------------- explanation / I4


def _random_case(rng):
    n = int(rng.integers(5, 60))
    gaps = [None if rng.random() < 0.05 else float(g) for g in rng.uniform(-1, 9, n)]
    delays = [None if rng.random() < 0.05 else float(d) for d in rng.gamma(1.2, 2, 80)]
    lines = rng.choice(["IC1", "IC5"], 80)
    a = pd.concat([arrs(delays[i : i + 1], line=str(lines[i]), start="07:00")
                   for i in range(80)], ignore_index=True)  # fmt: skip
    return conns(gaps), a


def test_explanations_truth_at_least_beta_and_verify_answer():
    rng = np.random.default_rng(7)
    for _ in range(25):
        c, a = _random_case(rng)
        for margin in (3, 5, 8):
            ans = answer(Q(margin_min=margin), c, a, VOCAB, CONFIG)
            assert all(e.truth >= BETA for e in ans.explanations)
            assert len([e for e in ans.explanations if e.restriction not in
                        (OWN_CONNECTIONS, OWN_ARRIVALS)]) <= 3  # fmt: skip
            assert verify_answer(ans, c, a, VOCAB, CONFIG)


def test_first_explanation_is_the_p_miss_sentence():
    a = answer(Q(), conns([4.0] * 30), arrs([0.0] * 40), VOCAB, CONFIG)
    e = a.explanations[0]
    assert (e.restriction, e.quantifier, e.truth) == (OWN_CONNECTIONS, "few", 1.0)
    assert e.sentence == "With 4 minutes to change, few of your connections at Olten are missed."
    assert e.summarizer == "connection_slack_minutes:missed" and e.n == 30


def test_verify_answer_detects_tampering():
    c, a = conns([1.0] * 13 + [4.0] * 12), arrs([0.0, 1.0, 2.5] * 20)
    ans = answer(Q(), c, a, VOCAB, CONFIG)
    assert verify_answer(ans, c, a, VOCAB, CONFIG)
    bad = ans.model_copy(update={"explanations": [ans.explanations[0].model_copy(
        update={"truth": ans.explanations[0].truth - 1e-6})]})  # fmt: skip
    assert not verify_answer(bad, c, a, VOCAB, CONFIG)
    assert not verify_answer(ans.model_copy(update={"decision": "safe"}), c, a, VOCAB, CONFIG)
    assert not verify_answer(ans.model_copy(update={"p_miss": 0.0}), c, a, VOCAB, CONFIG)


def test_summaries_mined_with_the_hub_as_segment_and_hub_selected_by_id():
    cfg = copy.deepcopy(CONFIG)
    cfg["connections"]["hub_stop_ids"] = {"Olten": ["8500218"]}
    hub = arrs([0.0] * 40)  # IC1 at Olten, all on time
    network = arrs([9.0] * 4000, stop_id="8507000", stop_name="Bern")  # far bigger elsewhere
    impostor = arrs([20.0] * 40, stop_id="8599999")  # named "Olten", other stop id
    a = answer(Q(), conns([4.0] * 30), pd.concat([hub, network, impostor], ignore_index=True),
               VOCAB, cfg)  # fmt: skip
    mined = [e for e in a.explanations if e.restriction != OWN_CONNECTIONS]
    assert mined, "expected hub summaries"
    for e in mined:
        assert e.n <= 40 and e.coverage == 1.0  # coverage relative to the hub, not the network
        if e.summarizer.endswith(":very_late"):  # impostor's 20-min delays are not at the hub
            assert e.quantifier == "few"
    assert verify_answer(a, conns([4.0] * 30), pd.concat([hub, network, impostor]), VOCAB, cfg)


def test_crisp_view_attached_when_arrivals_exist():
    a = answer(Q(), conns([4.0] * 30), arrs([0.0] * 30), VOCAB, CONFIG)
    assert a.crisp_decision == "safe" and a.crisp_sentences


# --------------------------------------------------------------------- I4 on the fixture


def test_invariant_i4_registered_and_passes_on_fixture(tmp_path):
    from urban_computing.evaluation import invariants  # noqa: F401  (registers I4)

    assert "I4" in registry.INVARIANTS
    interim, processed = tmp_path / "interim", tmp_path / "processed"
    interim.mkdir()
    processed.mkdir()
    fixtures = ROOT / "tests" / "fixtures" / "ist_sample"
    ctx = registry.Context(
        config=CONFIG,
        sample=True,
        paths={"raw_dir": str(fixtures), "service_points_dir": str(fixtures),
               "interim_dir": str(interim), "processed_dir": str(processed),
               "arrivals": str(processed / "arrivals.parquet"),
               "connections": str(processed / "connections.parquet"),
               "vocabulary": str(ROOT / "config" / "vocabulary.yaml")},
        seed=CONFIG["study"]["seed"],
    )  # fmt: skip
    result = registry.INVARIANTS["I4"](ctx)
    assert result.passed, result.details
    assert result.details["answers"] > 0 and result.details["n_failed"] == 0
    assert 0 <= result.details["vocabulary_gap_answers"] <= result.details["answers"]

    # the borderline fixture segment: Zürich HB IC1, 13 x 3 min late, 12 on time
    arrivals, connections, hub_ids = ctx.cache["i4_tables"]
    cfg = copy.deepcopy(CONFIG)
    cfg["connections"]["hub_stop_ids"] = hub_ids
    q = dict(hub="Zürich HB", arr_line="IC1", time_band="morning_peak", weekday_group="all")
    tight = answer(Q(**q, margin_min=3), connections, arrivals, VOCAB, cfg)
    loose = answer(Q(**q, margin_min=10), connections, arrivals, VOCAB, cfg)
    assert tight.decision != loose.decision  # margin matters on the borderline segment
    assert verify_answer(tight, connections, arrivals, VOCAB, cfg)


def test_methods_section_5_documents_the_rule():
    sec5 = (ROOT / "docs" / "methods.md").read_text().split("## 5.")[1].split("## 6.")[0]
    for token in ("p_miss", "margin", "actual gap", "−∞", "0.05", "0.30", "argmax", "cautious",
                  "20", "D-029", "I4"):  # fmt: skip
        assert token in sec5, token


# --------------------------------------------------------------------- review #56: gaps


def _connections_for(p_target: float, n: int = 40) -> pd.DataFrame:
    """n connections of which round(p n) are clearly missed (slack -2) and the rest
    clearly made (slack 2), with margin 4 and min transfer 2: p_miss = k / n exactly."""
    k = round(p_target * n)
    return conns([0.0] * k + [4.0] * (n - k))


@pytest.mark.parametrize("p", [0.25, 0.30, 0.35, 0.65])
def test_vocabulary_gap_still_explains_p_miss(p):
    c, a = _connections_for(p), arrs([0.0] * 40)
    ans = answer(Q(), c, a, VOCAB, CONFIG)
    assert ans.p_miss == pytest.approx(p)
    own = [e for e in ans.explanations if e.restriction == OWN_CONNECTIONS]
    assert len(own) == 1, ans.explanations  # always a sentence on the own connections
    e = own[0]
    k = round(p * 40)
    assert e.quantifier == "count" and e.n == 40
    assert e.sentence == (
        f"With 4 minutes to change, {k} of your 40 connections at Olten "
        f"({round(100 * k / 40)}%) were missed."
    )
    assert all(x.truth >= BETA for x in ans.explanations)  # never a word below beta
    assert verify_answer(ans, c, a, VOCAB, CONFIG)


def test_count_sentence_verified_exactly_and_only_in_the_gap():
    c, a = _connections_for(0.30), arrs([0.0] * 40)
    ans = answer(Q(), c, a, VOCAB, CONFIG)
    first = ans.explanations[0]
    wrong = first.model_copy(update={"sentence": first.sentence.replace("12 of", "11 of")})
    assert not verify_answer(ans.model_copy(update={"explanations": [wrong]}), c, a, VOCAB,
                             CONFIG)  # fmt: skip
    assert not verify_answer(ans.model_copy(update={"explanations": ans.explanations[1:]}), c,
                             a, VOCAB, CONFIG)  # own sentence missing  # fmt: skip
    # outside the gap the fuzzy word is used, and a count sentence would be rejected
    c2 = _connections_for(0.0)
    ok = answer(Q(), c2, a, VOCAB, CONFIG)
    assert ok.explanations[0].quantifier == "few"
    fake = first.model_copy(update={"sentence": "With 4 minutes to change, 0 of your 40 "
                                    "connections at Olten (0%) were missed."})  # fmt: skip
    assert not verify_answer(ok.model_copy(update={"explanations": [fake]}), c2, a, VOCAB, CONFIG)


def test_vocabulary_gap_fallback_wording():
    few = conns([4.0] * 5)  # < 20 connections -> arrivals fallback
    delays = [5.0] * 12 + [0.0] * 28  # 30 % arrive >= 4 min late
    ans = answer(Q(), few, arrs(delays), VOCAB, CONFIG)
    assert ans.provenance.fallback and ans.p_miss == pytest.approx(0.30)
    e = ans.explanations[0]
    assert e.restriction == OWN_ARRIVALS and e.quantifier == "count"
    assert e.sentence == ("With 4 minutes to change, 12 of 40 IC1 arrivals at Olten (30%) were "
                          "too late for your transfer.")  # fmt: skip
    assert verify_answer(ans, few, arrs(delays), VOCAB, CONFIG)


def test_every_answer_has_an_own_sentence_across_p():
    a = arrs([0.0] * 40)
    for k in range(0, 41):
        c = conns([0.0] * k + [4.0] * (40 - k))
        ans = answer(Q(), c, a, VOCAB, CONFIG)
        assert any(e.restriction == OWN_CONNECTIONS for e in ans.explanations), k
        assert all(e.truth >= BETA for e in ans.explanations)
        assert verify_answer(ans, c, a, VOCAB, CONFIG)
