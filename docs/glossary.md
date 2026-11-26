# Plain-language glossary (for data engineers)

**Fuzzy set / membership function.** A function that returns a score in [0, 1] instead of
true/false. `on_time(delay)` is 1 for ≤ 1 min, 0.5 at 2 min, 0 at ≥ 3 min. SBB's rule
`delay < 3` is the crisp (true/false) version. Think: a soft `CASE WHEN`.

**Linguistic variable / summarizer.** A named family of such functions over one column:
`arrival_delay` → {on_time, slightly_late, late, very_late}.

**Fuzzy quantifier.** A function over a *proportion*: `most(p)` is 0 below 0.5 and 1 above
0.85. Words: few, about half, most.

**Linguistic summary (protoform).** A sentence "Q of the x are S", e.g. "Most trains are on
time". Its **truth (validity)** is `v = Q(mean(S(x_i)))`. Deterministic, recomputable from
raw data.

**Restriction.** A soft `WHERE`: "Q of the R x are S" ("Most *morning-peak IC* arrivals are
on time"). Truth: `v = Q( sum(t(R(x_i), S(x_i))) / sum(R(x_i)) )`, t = product or min.

**Coverage (Hudec).** How much of the data a summary rests on. A summary can be true but
based on 8 trains out of 2 million; coverage catches that. **Quality Qc** combines truth and
coverage and is 0 when coverage is too low.

**Computing with Words (Zadeh).** Computing where inputs and outputs are words whose meaning
is a fuzzy set. **Perceptual Computer (Mendel):** encoder (data/words → fuzzy sets) → CWW
engine → decoder (back to words). Our mapping: arrivals/connections → summaries + truth →
decision word + explanation sentences.

**Perception-aware "late".** "Late" depends on the person: with a 4-minute transfer a
3-minute delay is risky; without a connection it is fine. We shift the membership function
by the passenger's margin.

**Crisp checker vs fuzzy checker.** Crisp: "most" is true iff > 50% (Stat-to-Text style).
Fuzzy: "most" has a truth degree. Borderline cases (52% late → crisp "true", fuzzy ≈ 0.1)
are where they disagree.

**Faithful by construction.** The assistant's decision and its explanation sentences are
computed by the same truth function, so the explanation cannot contradict how the decision
was made (unlike an LLM explaining after the fact).
