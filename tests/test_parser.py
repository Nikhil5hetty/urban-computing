"""UC-041: LLM output -> claims. Hand-written examples, deterministic lexicon, no LLM."""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import pytest
import yaml

from urban_computing.fuzzy.vocabulary import load_vocabulary
from urban_computing.llm.parser import claim_stats, load_lexicon, parse_output

ROOT = Path(__file__).resolve().parents[1]
LEX = load_lexicon()

D = "arrival_delay_minutes"
C = "connection_slack_minutes"
MON = "weekday_group=monday"  # "Monday mornings": bare "mornings" = own segment (D-022)


def _j(*claims: dict, text: str = "") -> str:
    return json.dumps({"claims": list(claims), "text": text})


def _q(q, s, r=None):
    return {"quantifier": q, "summarizer": s, "restriction": r}


def _key(c):
    return (c.quantifier, c.summarizer, c.restriction, c.status, c.source)


# (raw output, expected [(quantifier, summarizer, restriction, status, source), ...])
EXAMPLES = [
    # ---------------- JSON path (validated against the lexicon)
    ("j01", _j(_q("most", "on time")), [("most", f"{D}:on_time", None, "ok", "json")]),
    ("j02", _j(_q("few", "missed")), [("few", f"{C}:missed", None, "ok", "json")]),
    (
        "j03",
        _j(_q("about half", "slightly late", "Monday mornings")),
        [("about_half", f"{D}:slightly_late", MON, "ok", "json")],
    ),
    (
        "j04",
        _j(_q("about_half", "arrival_delay_minutes:late", "weekday_group=friday")),
        [("about_half", f"{D}:late", "weekday_group=friday", "ok", "json")],
    ),
    (
        "j05",
        _j(_q("Most", "Very Late", "evening peak")),
        [("most", f"{D}:very_late", "time_band=evening_peak", "ok", "json")],
    ),
    (
        "j06",
        _j(_q("most", "tight"), _q("few", "comfortable")),
        [
            ("most", f"{C}:tight", None, "ok", "json"),
            ("few", f"{C}:comfortable", None, "ok", "json"),
        ],
    ),
    ("j07", _j(_q("many", "late")), [(None, f"{D}:late", None, "unverifiable", "json")]),
    ("j08", _j(_q("most", "crowded")), [("most", None, None, "unverifiable", "json")]),
    (
        "j09",
        _j(_q("most", "late", "during the holidays")),
        [("most", f"{D}:late", None, "unverifiable", "json")],
    ),
    ("j10", _j({"quantifier": "most"}), [("most", None, None, "unverifiable", "json")]),
    ("j11", _j("most trains are late"), [(None, None, None, "unverifiable", "json")]),
    (
        "j12",
        _j(_q("most", "late because of construction")),
        [("most", f"{D}:late", None, "unverifiable_causal", "json")],
    ),
    (
        "j13",
        "Here is my answer:\n```json\n" + _j(_q("few", "missed")) + "\n```",
        [("few", f"{C}:missed", None, "ok", "json")],
    ),
    (
        "j14",
        _j(_q("most", "on time"), text="Most trains are on time."),
        [("most", f"{D}:on_time", None, "ok", "json")],
    ),  # text restates JSON: no duplicate
    (
        "j15",
        _j(_q("most", "on time")) + "\nYou should be fine.",
        [("most", f"{D}:on_time", None, "ok", "json")],
    ),
    (
        "j16",
        _j(_q("most", "on time"), text="Delays happen because of the weather."),
        [
            ("most", f"{D}:on_time", None, "ok", "json"),
            (None, None, None, "unverifiable_causal", "lexicon"),
        ],
    ),
    ("j17", _j(_q("almost all", "on time")), [("most", f"{D}:on_time", None, "ok", "json")]),
    (
        "j18",
        _j(_q("most", "on time", "weekend mornings")),
        [("most", f"{D}:on_time", "weekday_group=weekend", "ok", "json")],
    ),
    ("j19", _j(), []),  # valid but empty
    (
        "j20",
        '{"claims": "none"} Most trains are on time.',
        [("most", f"{D}:on_time", None, "ok", "lexicon")],
    ),  # invalid schema -> free text
    # ---------------- lexicon path (free text only)
    ("t01", "Most trains arrive on time.", [("most", f"{D}:on_time", None, "ok", "lexicon")]),
    (
        "t02",
        "The majority of your trains are punctual.",
        [("most", f"{D}:on_time", None, "ok", "lexicon")],
    ),
    (
        "t03",
        "A handful of connections are missed.",
        [("few", f"{C}:missed", None, "ok", "lexicon")],
    ),
    (
        "t04",
        "Roughly half of the Monday morning trains are slightly late.",
        [("about_half", f"{D}:slightly_late", MON, "ok", "lexicon")],
    ),
    (
        "t05",
        "Most trains are a few minutes late.",
        [("most", f"{D}:slightly_late", None, "ok", "lexicon")],
    ),  # "a few" inside summarizer
    (
        "t06",
        "On Fridays, few trains are very late.",
        [("few", f"{D}:very_late", "weekday_group=friday", "ok", "lexicon")],
    ),
    (
        "t07",
        "Hardly any connections are missed in the early morning.",
        [("few", f"{C}:missed", "time_band=early", "ok", "lexicon")],
    ),
    (
        "t08",
        "Your transfer is usually comfortable.",
        [("most", f"{C}:comfortable", None, "ok", "lexicon")],
    ),
    ("t09", "Most trains are not late.", [("most", f"{D}:late", None, "unverifiable", "lexicon")]),
    ("t10", "Trains are often delayed.", [(None, None, None, "unverifiable", "lexicon")]),
    (
        "t11",
        "About 18% of connections are missed.",
        [(None, f"{C}:missed", None, "unverifiable", "lexicon")],
    ),
    (
        "t12",
        "Delays at Olten are mostly due to construction work.",
        [("most", None, None, "unverifiable_causal", "lexicon")],
    ),
    (
        "t13",
        "Most trains are on time or slightly late.",
        [("most", None, None, "unverifiable", "lexicon")],
    ),  # two summarizers
    (
        "t14",
        "Most trains on Mondays and Fridays are late.",
        [("most", f"{D}:late", None, "unverifiable", "lexicon")],
    ),  # two keys, one family
    ("t15", "Have a good trip!", []),
    (
        "t16",
        "Most IC1 trains are on time. Few connections to the IR16 are missed. Enjoy!",
        [
            ("most", f"{D}:on_time", None, "ok", "lexicon"),
            ("few", f"{C}:missed", None, "ok", "lexicon"),
        ],
    ),
    ("t17", "", []),
]


@pytest.mark.parametrize("name,raw,expected", EXAMPLES, ids=[e[0] for e in EXAMPLES])
def test_hand_written_examples(name, raw, expected):
    claims = parse_output(name, raw, LEX)
    assert [_key(c) for c in claims] == expected
    assert [c.slot for c in claims] == list(range(len(claims)))
    assert all(c.question_id == name for c in claims)


def test_at_least_30_examples_cover_both_paths():
    sources = {src for *_, exp in EXAMPLES for (*_, src) in exp}
    assert len(EXAMPLES) >= 30 and sources == {"json", "lexicon"}
    assert sum(1 for n, *_ in EXAMPLES if n.startswith("j")) >= 15
    assert sum(1 for n, *_ in EXAMPLES if n.startswith("t")) >= 15


# --------------------------------------------------------------------- inconsistency


def test_json_contradicting_free_text_flags_both():
    raw = _j(_q("most", "on time"), text="Few trains are on time.")
    claims = parse_output("q", raw, LEX)
    assert [_key(c) for c in claims] == [
        ("most", f"{D}:on_time", None, "inconsistent", "json"),
        ("few", f"{D}:on_time", None, "inconsistent", "lexicon"),
    ]


def test_contradiction_in_text_outside_the_block():
    raw = "Few connections are missed.\n" + _j(_q("most", "missed"))
    statuses = [(c.source, c.status) for c in parse_output("q", raw, LEX)]
    assert statuses == [("json", "inconsistent"), ("lexicon", "inconsistent")]


def test_different_restriction_is_not_a_contradiction():
    raw = _j(_q("most", "on time"), text="Few trains are on time on Mondays.")
    claims = parse_output("q", raw, LEX)
    assert [c.status for c in claims] == ["ok", "ok"]
    assert claims[1].restriction == "weekday_group=monday"


# --------------------------------------------------------------------- statistic


def test_unverifiable_rate_is_returned():
    claims = parse_output("q", _j(_q("most", "on time"), _q("many", "late"),
                                  _q("most", "late because of rain")), LEX)  # fmt: skip
    stats = claim_stats(claims)
    assert stats["n"] == 3 and stats["ok"] == 1
    assert stats["unverifiable"] == 1 and stats["unverifiable_causal"] == 1
    assert stats["unverifiable_rate"] == pytest.approx(2 / 3)


def test_stats_over_many_outputs_and_empty():
    all_claims = [c for name, raw, _ in EXAMPLES for c in parse_output(name, raw, LEX)]
    stats = claim_stats(all_claims)
    assert stats["n"] == len(all_claims)
    assert (
        stats["ok"] + stats["unverifiable"] + stats["unverifiable_causal"] + stats["inconsistent"]
        == stats["n"]
    )
    assert math.isnan(claim_stats([])["unverifiable_rate"])


# --------------------------------------------------------------------- determinism / config


def test_deterministic_and_no_llm_imports():
    raw = EXAMPLES[2][1] + " Most trains are a few minutes late."
    assert parse_output("q", raw, LEX) == parse_output("q", raw, LEX)
    src = (ROOT / "src" / "urban_computing" / "llm" / "parser.py").read_text()
    imported = {
        (n.module or "") if isinstance(n, ast.ImportFrom) else a.name
        for n in ast.walk(ast.parse(src))
        if isinstance(n, (ast.Import, ast.ImportFrom))
        for a in (n.names if isinstance(n, ast.Import) else [None])
    }
    roots = {m.split(".")[0] for m in imported if m}
    assert not roots & {"transformers", "torch", "vllm", "openai", "anthropic", "random"}


def test_lexicon_maps_only_to_vocabulary_and_study_keys():
    vocab = load_vocabulary(ROOT / "config" / "vocabulary.yaml")
    study = yaml.safe_load((ROOT / "config" / "study.yaml").read_text())
    quants = {w for words in vocab.quantifiers.values() for w in words}
    summs = {f"{a}:{w}" for a, words in vocab.summarizers.items() for w in words}
    assert set(LEX["quantifiers"]) <= quants
    assert set(LEX["summarizers"]) == summs  # every vocabulary word can be parsed
    assert set(LEX["restrictions"]["time_band"]) == set(study["time_bands"])
    assert set(LEX["restrictions"]["weekday_group"]) <= {"weekday", "monday", "friday",
                                                         "weekend", "all"}  # fmt: skip


def test_custom_lexicon_needs_no_code_change():
    lex = {"quantifiers": {"most": ["the lion's share of"]},
           "summarizers": {f"{D}:on_time": ["on the dot"]}}  # fmt: skip
    claims = parse_output("q", "The lion's share of trains run on the dot.", lex)
    assert [_key(c) for c in claims] == [("most", f"{D}:on_time", None, "ok", "lexicon")]


@pytest.mark.parametrize("bad", [None, {}, {"quantifiers": {}}, {"summarizers": {"x": ["y"]}}])
def test_malformed_lexicon_raises(bad):
    with pytest.raises(ValueError):
        parse_output("q", "Most trains are on time.", bad)


# --------------------------------------------------------------------- review #40 (D-022)


@pytest.mark.parametrize(
    "sentence,quantifier",
    [
        ("Very few trains are late in the morning.", "few"),
        ("Hardly any connections are missed.", "few"),
        ("Almost no trains are very late.", "few"),
        ("Almost all trains are on time.", "most"),
        ("Nearly all connections are comfortable.", "most"),
        ("Trains are almost always on time.", "most"),
    ],
)
def test_default_lexicon_maps_only_to_core_quantifiers(sentence, quantifier):
    (claim,) = parse_output("q", sentence, LEX)
    assert (claim.quantifier, claim.status) == (quantifier, "ok")


def test_core_lexicon_never_yields_extended_words():
    assert set(LEX["quantifiers"]) == {"few", "about_half", "most"}
    assert "quantifiers_extended" not in LEX
    raws = [raw for _, raw, _ in EXAMPLES] + ["Virtually no trains are late."]
    quants = {c.quantifier for r in raws for c in parse_output("q", r, LEX)}
    assert quants <= {None, "few", "about_half", "most"}


@pytest.mark.parametrize(
    "sentence,quantifier",
    [
        ("Very few trains are late.", "almost_none"),
        ("Hardly any connections are missed.", "almost_none"),
        ("Almost all trains are on time.", "almost_all"),
        ("Nearly always the connection is comfortable.", "almost_all"),
        ("A few trains are late.", "few"),  # unchanged core phrase
        ("Most trains are late.", "most"),
    ],
)
def test_extended_lexicon_for_ablation(sentence, quantifier):
    ext = load_lexicon(quantifier_set="extended")
    (claim,) = parse_output("q", sentence, ext)
    assert claim.quantifier == quantifier
    (json_claim,) = parse_output("q", _j(_q("almost all", "late")), ext)
    assert json_claim.quantifier == "almost_all"


def test_bad_quantifier_set_raises():
    with pytest.raises(ValueError):
        load_lexicon(quantifier_set="all")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "raw,summarizer",
    [
        ("Most morning trains are delayed.", None),
        ("Most trains run behind schedule.", None),
        ("Most trains have delays.", None),
        (_j(_q("most", "delayed")), None),
        ("Most trains are slightly delayed.", f"{D}:slightly_late"),
        ("Few trains are badly delayed.", f"{D}:very_late"),
        ("Few trains are severely delayed.", f"{D}:very_late"),
        ("Most trains are late.", f"{D}:late"),
    ],
)
def test_bare_delayed_is_ambiguous_qualified_forms_map(raw, summarizer):
    (claim,) = parse_output("q", raw, LEX)
    assert claim.summarizer == summarizer
    assert claim.status == ("ok" if summarizer else "unverifiable")


@pytest.mark.parametrize(
    "raw,restriction",
    [
        ("Most evening trains are on time.", None),
        ("Most morning trains are on time.", None),
        ("In the mornings most trains are on time.", None),
        ("At rush hour most trains are on time.", None),
        (_j(_q("most", "on time", "evening")), None),
        (_j(_q("most", "on time", "Monday mornings")), "weekday_group=monday"),
        ("Most trains in the evening peak are on time.", "time_band=evening_peak"),
        ("Most trains in the morning rush hour are on time.", "time_band=morning_peak"),
        ("Most trains in the early morning are on time.", "time_band=early"),
        ("Most trains in the late evening are on time.", "time_band=evening"),
        ("Most trains at night are on time.", "time_band=night"),
    ],
)
def test_bare_time_words_mean_own_segment(raw, restriction):
    (claim,) = parse_output("q", raw, LEX)
    assert (claim.restriction, claim.status) == (restriction, "ok")
    # "late evening" is a restriction, not the summarizer "late"
    assert claim.summarizer == f"{D}:on_time"


def test_decision_d022_is_proposed():
    rows = [
        ln for ln in (ROOT / "docs" / "decisions.md").read_text().splitlines()
        if ln.startswith("| D-022 ")
    ]  # fmt: skip
    assert len(rows) == 1 and "| proposed |" in rows[0]
