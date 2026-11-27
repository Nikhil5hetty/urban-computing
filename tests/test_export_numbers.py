"""UC-070: results.json -> paper/numbers.tex macros, and invariant I6 (no hard-coded numbers)."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


i6 = _load("check_paper_numbers")
exp = _load("export_paper_numbers")

SAMPLE = {
    "hypotheses": {
        "H1a": {
            "point": 0.14,
            "ci_low": 0.1149,
            "ci_high": 0.172,
            "p": 0.0004,
            "value": None,
            "verdict": "not_supported",
        },
        "H1b": {
            "point": None,
            "ci_low": None,
            "ci_high": None,
            "p": None,
            "value": 7.0,
            "verdict": "supported",
        },
        "H3c": {
            "point": 0.231,
            "ci_low": 0.18,
            "ci_high": 0.29,
            "p": 0.0312,
            "value": None,
            "verdict": "inconclusive",
        },
    },  # fmt: skip
    "invariants": {"I1": "pass", "I2": "pass", "I3": "not run"},
    "meta": {
        "git_sha": "14e3e7ab967f580cb7a7",
        "config_hash": "55393a4cc98ac948fcd7",
        "sample": False,
    },  # fmt: skip
    "tables": {},
}


def _macros(tex: str) -> dict[str, str]:
    return dict(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}$", tex, re.MULTILINE))


# --------------------------------------------------------------------- macro names


@pytest.mark.parametrize(
    "ident,base",
    [("H1a", "Honea"), ("H2b", "Htwob"), ("H3c", "Hthreec"), ("I6", "Isix"), ("I10", "Ionezero")],
)
def test_macro_names_derive_from_ids(ident, base):
    assert exp.macro_base(ident) == base


@pytest.mark.parametrize("bad", ["1H", "H-1", "H 1", ""])
def test_invalid_ids_raise(bad):
    with pytest.raises(ValueError):
        exp.macro_base(bad)


def test_every_preregistered_id_gets_macros():
    spec = yaml.safe_load((ROOT / "eval" / "hypotheses.yaml").read_text())
    m = _macros(exp.render(exp.placeholder_results()))
    for h in spec["hypotheses"]:
        base = exp.macro_base(h["id"])
        for suffix in ("Point", "CILow", "CIHigh", "CI", "P", "Value", "Verdict"):
            assert f"{base}{suffix}" in m
    for inv in spec["invariants"]:
        if inv["id"] != "I6":
            assert f"{exp.macro_base(inv['id'])}Status" in m


# --------------------------------------------------------------------- values


def test_values_from_sample_results():
    m = _macros(exp.render(SAMPLE))
    assert m["HoneaPoint"] == "0.14"
    assert (m["HoneaCILow"], m["HoneaCIHigh"], m["HoneaCI"]) == ("0.11", "0.17", "[0.11, 0.17]")
    assert m["HoneaP"] == "$<$ 0.001" and m["HthreecP"] == "0.031"
    assert m["HoneaVerdict"] == "not supported" and m["HthreecVerdict"] == "inconclusive"
    assert m["HonebValue"] == "7" and m["HonebPoint"] == "--" and m["HonebCI"] == "--"
    assert (m["IoneStatus"], m["IthreeStatus"]) == ("pass", "not run")
    assert m["ResultsGitSha"] == "14e3e7a" and m["ResultsConfigHash"] == "55393a4cc98a"
    assert m["ResultsSample"] == "no" and m["ResultsBanner"] == ""


def test_sample_results_get_a_banner():
    m = _macros(exp.render({**SAMPLE, "meta": {**SAMPLE["meta"], "sample": True}}))
    assert m["ResultsSample"] == "yes" and "not for submission" in m["ResultsBanner"]


def test_render_is_deterministic():
    assert exp.render(SAMPLE) == exp.render(dict(reversed(list(SAMPLE.items()))))


def test_failed_invariant_blocks_export(tmp_path):
    bad = {**SAMPLE, "invariants": {"I1": "pass", "I4": "fail"}}
    with pytest.raises(RuntimeError, match="I4"):
        exp.render(bad)
    import json

    res = tmp_path / "results.json"
    res.write_text(json.dumps(bad))
    out = tmp_path / "paper" / "numbers.tex"
    out.parent.mkdir()
    assert exp.export(res, out) == 2 and not out.exists()


def test_export_end_to_end_and_missing_results(tmp_path):
    import json

    res = tmp_path / "results.json"
    res.write_text(json.dumps(SAMPLE))
    out = tmp_path / "paper" / "numbers.tex"
    out.parent.mkdir()
    assert exp.main(["--results", str(res), "--out", str(out)]) == 0
    m = _macros(out.read_text())
    assert m["IsixStatus"] == "pass" and m["HoneaPoint"] == "0.14"
    assert exp.export(tmp_path / "nope.json", out) == 2


def test_make_paper_numbers_target_runs_the_export():
    mk = (ROOT / "Makefile").read_text()
    target = mk[mk.index("\npaper-numbers:") :].split("\n\n")[0]
    assert "scripts/export_paper_numbers.py" in target


# --------------------------------------------------------------------- I6 checker


def test_i6_flags_decimals_outside_numbers_and_tables(tmp_path):
    (tmp_path / "sections").mkdir()
    (tmp_path / "tables").mkdir()
    (tmp_path / "sections" / "a.tex").write_text(
        "Truth was 0.74 here.\n"  # flagged
        "Share 3,5 and .5 too.\n"  # flagged twice
        "% a comment with 0.99 is ignored\n"
        "Escaped 12\\% then 1.5 after.\n"  # \\% is not a comment: both flagged
        "In 2026, Section 3 and the 3-minute rule are fine.\n"
    )
    (tmp_path / "numbers.tex").write_text("\\newcommand{\\X}{0.74}\n")
    (tmp_path / "tables" / "t.tex").write_text("0.12 & 0.34\n")
    found = [(v.line, v.text) for v in i6.check(tmp_path)]
    assert found == [(1, "0.74"), (2, "3,5"), (2, ".5"), (4, "12\\%"), (4, "1.5")]
    assert i6.main(["--paper-dir", str(tmp_path)]) == 1
    (tmp_path / "sections" / "a.tex").write_text("No numbers: \\HoneaPoint.\n")
    assert i6.main(["--paper-dir", str(tmp_path)]) == 0


def test_repository_paper_passes_i6():
    assert i6.check(PAPER) == []


# --------------------------------------------------------------------- skeleton


def _tex_sources() -> str:
    return "\n".join(p.read_text() for p in sorted(PAPER.rglob("*.tex")) if p.name != "numbers.tex")


def test_skeleton_structure():
    main = (PAPER / "main.tex").read_text()
    assert "\\documentclass[manuscript" in main and "{acmart}" in main
    assert "\\citestyle{acmauthoryear}" in main and "\\input{numbers}" in main
    src = _tex_sources()
    for title in ("Introduction", "Background and Related Work", "Concept", "Prototype",
                  "Empirical Study", "Discussion", "Limitations", "Conclusion",
                  "Declaration on the Use of Generative AI"):  # fmt: skip
        assert re.search(r"\\section\*?\{" + re.escape(title), src), title
    assert "\\appendix" in main
    assert not re.search(r"\\(sub)?paragraph\{|\\subsubsubsection", src)  # <= 3 levels


def test_abstract_about_150_words_and_keywords():
    main = (PAPER / "main.tex").read_text()
    abstract = main.split("\\begin{abstract}")[1].split("\\end{abstract}")[0]
    words = re.sub(r"\\placeholder\{[^}]*\}|%.*", "", abstract).split()
    assert 130 <= len(words) <= 180, len(words)
    assert re.search(r"\\keywords\{[^}]+,", main)


def test_cited_keys_exist_in_bibliography():
    bib = (PAPER / "references.bib").read_text()
    keys = set(re.findall(r"@\w+\{([^,]+),", bib))
    cited = {k.strip() for c in re.findall(r"\\cite[pt]?\{([^}]*)\}", _tex_sources())
             for k in c.split(",")}  # fmt: skip
    assert cited and cited <= keys
    literature = (ROOT / "docs" / "literature.md").read_text()
    assert all(f"| {k} |" in literature for k in keys)  # only documented references


# --------------------------------------------------------------------- review #48


def _blocked(sample: bool) -> dict:
    hyps = {k: {**v, "verdict": "blocked_by_invariant"} for k, v in SAMPLE["hypotheses"].items()}
    return {**SAMPLE, "hypotheses": hyps,
            "invariants": {"I1": "pass", "I2": "pass", "I3": "pass"},
            "meta": {**SAMPLE["meta"], "sample": sample}}  # fmt: skip


def test_blocked_real_results_are_not_exported(tmp_path, capsys):
    import json

    res = tmp_path / "results.json"
    res.write_text(json.dumps(_blocked(sample=False)))
    out = tmp_path / "paper" / "numbers.tex"
    out.parent.mkdir()
    assert exp.export(res, out) == 2 and not out.exists()
    err = capsys.readouterr().err
    assert "H1a" in err and "I4 (missing)" in err and "I5 (missing)" in err
    with pytest.raises(RuntimeError, match="blocked"):
        exp.render(_blocked(sample=False))


def test_blocked_sample_results_still_export_with_banner(tmp_path):
    import json

    res = tmp_path / "results.json"
    res.write_text(json.dumps(_blocked(sample=True)))
    out = tmp_path / "paper" / "numbers.tex"
    out.parent.mkdir()
    assert exp.export(res, out) == 0
    m = _macros(out.read_text())
    assert m["ResultsSample"] == "yes" and "not for submission" in m["ResultsBanner"]
    assert m["HoneaVerdict"] == "blocked by invariant"


def test_real_results_with_all_invariants_export():
    ok = {**SAMPLE, "invariants": {i: "pass" for i in exp.REQUIRED_REAL}}
    assert "\\newcommand{\\HoneaPoint}{0.14}" in exp.render(ok)


def test_ci_level_from_config_alpha():
    assert _macros(exp.render(SAMPLE))["CILevel"] == "95\\%"
    assert _macros(exp.render(SAMPLE, alpha=0.1))["CILevel"] == "90\\%"


@pytest.mark.parametrize(
    "line,hit",
    [
        ("About 52\\% of arrivals were late, based on 38 trains.", "52\\%"),
        ("About 52 \\% of arrivals.", "52 \\%"),
        ("About 52 percent of arrivals.", "52 percent"),
        ("About 52 per cent of arrivals.", "52 per cent"),
        ("About 52.5\\% of arrivals.", "52.5\\%"),  # one hit, not two
    ],
)
def test_i6_flags_hand_typed_percentages(tmp_path, line, hit):
    (tmp_path / "r.tex").write_text(line + "\n")
    assert [v.text for v in i6.check(tmp_path)] == [hit]


def test_citednum_escape_for_cited_literature(tmp_path):
    (tmp_path / "r.tex").write_text(
        "The operator reports \\citednum{94\\%} punctuality \\citep{x} and "
        "\\citednum{2.5} min average delay; our share is \\HoneaPoint.\n"
        "Counts like 38 trains are not checked (review).\n"
    )
    assert i6.check(tmp_path) == []
    (tmp_path / "r.tex").write_text("\\citednum{94\\%} but also 61\\% hand-typed.\n")
    assert [v.text for v in i6.check(tmp_path)] == ["61\\%"]
    assert "\\newcommand{\\citednum}" in (PAPER / "main.tex").read_text()
    readme = (PAPER / "README.md").read_text()
    assert "\\citednum" in readme and "integer counts" in readme.lower()
