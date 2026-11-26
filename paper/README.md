# Paper (UC-070 skeleton; text by UC-071, UC-072, UC-061)

ACM `acmart`, single-column manuscript (`manuscript,screen,nonacm`), author-year citations
(`\citestyle{acmauthoryear}`), Human-IST seminar guidelines. At most three heading levels
(section, subsection, subsubsection).

## Build

```bash
make eval            # or: make eval-sample (synthetic fixture; the paper shows a red banner)
make paper-numbers   # results/results.json -> paper/numbers.tex, then checks I6
cd paper && latexmk -pdf main.tex          # TeX Live
cd paper && tectonic main.tex              # or Tectonic (downloads packages on first run)
```

Without any results yet: `uv run python scripts/export_paper_numbers.py --placeholder`
writes `numbers.tex` with every macro set to `--`, so the skeleton still compiles.
`numbers.tex` is generated and not committed. CI does not build the PDF (no TeX in CI);
the export and the I6 check are tested in `tests/test_export_numbers.py`.

## Numbers (invariant I6)

Every number in the paper comes from `results/results.json` through the macros in
`numbers.tex`. Macro names derive from the ids: digits are spelled out, so hypothesis `H1a`
gives `\HoneaPoint`, `\HoneaCI`, `\HoneaCILow`, `\HoneaCIHigh`, `\HoneaP`, `\HoneaValue`,
`\HoneaVerdict`; invariant `I3` gives `\IthreeStatus`. Provenance: `\ResultsGitSha`,
`\ResultsConfigHash`, `\ResultsSample`, `\ResultsBanner`.

`scripts/check_paper_numbers.py` fails if a decimal number (`0.74`, `3,5`) appears in
`paper/**/*.tex` outside `numbers.tex` and `tables/` (comments ignored). Write measured
values only through macros or generated tables, and version numbers (models, libraries)
through a macro or a table as well. If any invariant in results.json failed, the export
refuses to write numbers (docs/evaluation.md §2.2).
