# Methods (filled by UC-020 … UC-023, UC-031, UC-042)

Every formula here cites its source (paper, equation or page). Agents: replace each
`TODO` with the final formula, parameters and a citation; do not invent formulas.

## 1. Vocabulary (UC-020)

Source of truth: `config/vocabulary.yaml`, loaded by
`urban_computing.fuzzy.vocabulary.load_vocabulary` (no code change needed when it changes).
Every word is a trapezoid [a, b, c, d]:

μ(x) = 0 for x ≤ a or x ≥ d; (x − a)/(b − a) for a < x < b; 1 for b ≤ x ≤ c;
(d − x)/(d − c) for c < x < d.

`null` in a/b (or c/d) is an open shoulder at −∞ (+∞). Triangles (b = c) and vertical edges
(a = b, c = d: crisp steps) are allowed; NaN input gives NaN. Loading rejects unordered
or half-open breakpoints and quantifier breakpoints outside [0, 1] (`ValueError`).

**Arrival delay** (actual − planned arrival, minutes). The four words form a Ruspini
partition: memberships sum to exactly 1 for every delay (checked on [−5, 30] min,
`tests/test_vocabulary.py`).

| Word | [a, b, c, d] | Justification |
|---|---|---|
| on_time | [−∞, −∞, 1, 3] | Reaches 0 at 3 min, the SBB punctuality boundary (< 3 min late = punctual, D-007), so fuzzy "on time" and the crisp rule agree that ≥ 3 min is not on time. Full membership up to 1 min is our design choice (μ = 0.5 at 2 min). |
| slightly_late | [1, 3, 3, 5] | Triangle peaking at the 3-min boundary; breakpoints chosen so the words form a partition with on_time and late. Design choice. |
| late | [3, 5, 8, 10] | Fully late from 5 to 8 min. Design choice, no external source. |
| very_late | [8, 10, +∞, +∞] | Fully very late from 10 min. Design choice, no external source. |

**Connection slack** ((actual departure of B − actual arrival of A) − minimum transfer time,
minutes; < 0 means the transfer was not possible). Also a Ruspini partition (sum = 1 on
[−5, 30] min).

| Word | [a, b, c, d] | Justification |
|---|---|---|
| missed | [−∞, −∞, −0.5, 0] | Fully missed at ≤ −0.5 min, not missed at slack ≥ 0. The 0.5-min ramp keeps slack values just below 0 partly "tight". Design choice. |
| tight | [−0.5, 0, 1, 2] | Fully tight for 0–1 min of slack. Design choice. |
| comfortable | [1, 2, +∞, +∞] | Fully comfortable from 2 min of slack. Design choice. |

**Quantifiers** (proportions in [0, 1]). The core words few / about half / most (and
β = 0.6 in `config/study.yaml`) follow Pincay et al. 2021 (D-008); the breakpoints are ours
because that paper shows the curves only graphically (D-008).

UC-002 read pincay2021 Figure 2 (p. 172, top panel "Quantifier Q") from the rendered PDF.
The paper gives no numbers, so the readings below are approximate (± 0.01). Its three
quantifiers form a uniform family with the grid 0.2 / 0.4 / 0.6 / 0.8 and crossovers at
0.3 and 0.7:

| Word | pincay2021 Fig. 2 (read off) | ours (`config/vocabulary.yaml`) |
|---|---|---|
| few | [−∞, −∞, 0.2, 0.4] | [−∞, −∞, 0.1, 0.35] |
| about_half | [0.2, 0.4, 0.6, 0.8] | [0.3, 0.45, 0.55, 0.7] |
| most ("most of") | [0.6, 0.8, +∞, +∞] | [0.5, 0.85, +∞, +∞] |

So our breakpoints do **not** match the baseline paper. Ours are narrower and sit closer to
½. Whether to switch is proposed decision D-028; the config is unchanged until the PM
decides (AGENTS §4.3).

For comparison, Hudec's "most of" is [0.5, 0.8, +∞, +∞]: hudec2018 Eq. (4), p. 985, and
hudec2022 Eq. (4), p. 325.

| Set | Word | [a, b, c, d] |
|---|---|---|
| core | few | [−∞, −∞, 0.1, 0.35] |
| core | about_half | [0.3, 0.45, 0.55, 0.7] |
| core | most | [0.5, 0.85, +∞, +∞] (monotone non-decreasing) |
| extended (ablation, UC-054) | almost_none | [−∞, −∞, 0.02, 0.1] |
| extended (ablation, UC-054) | almost_all | [0.85, 0.95, +∞, +∞] |

The quantifiers are deliberately *not* a Ruspini partition. Each summary's truth is computed
for one quantifier at a time (§2), so overlaps and gaps only mean that some proportions fit
two words partly, or no word fully. For the core set, the summed membership ranges from
0.20 (p = 0.30) to 1.14 (p = 0.55).

**Perception-aware lateness (SRQ2).** For a passenger with transfer margin m minutes, a delay
x is "late for my transfer" with

μ_m(x) = 0 for x ≤ m − s; (x − (m − s))/s for m − s < x < m; 1 for x ≥ m,

i.e. the trapezoid [m − s, m, +∞, +∞]. It is monotone in x, and s = 0 gives the crisp rule
x ≥ m. Spread s = 2 min (`perception.late_for_my_transfer.spread_minutes`) is a design
choice: a delay 2 min short of the margin is not yet felt as a risk.
(`Vocabulary.late_for_my_transfer(margin_min, spread_min=None)`).

## 2. Truth of linguistic summaries (UC-021)

Implementation: `urban_computing.fuzzy.truth` (NumPy, vectorised). Rows x_1 … x_n, summarizer
S, optional restriction R (both membership functions from §1), relative quantifier Q.

**Fuzzy proportion** (sigma-count; `fuzzy_proportion`):

- without restriction: p = (1/n) Σ_i μ_S(x_i)
- with restriction: p = Σ_i t(μ_R(x_i), μ_S(x_i)) / Σ_i μ_R(x_i), with t-norm
  t(a, b) = a·b (`product`, default, `config/study.yaml` `mining.tnorm`) or min(a, b)
  (`min`, ablation).

**Truth (validity)**:

- Protoform 1 "Q x are S": v = μ_Q(p), with p as above without R (`truth_simple`), i.e.
  v = μ_Q((1/n) Σ_i μ_S(x_i)).
  - Source: pincay2021, Eq. (2), §2.1, p. 170, which attributes it to Kacprzyk & Zadrożny
    (2009, IJSSCI 1(1)).
  - The same formula appears in hudec2018, Eqs. (5)–(6), p. 986, and in hudec2022,
    Eq. (5), p. 325; both cite Yager (1982).
  - The primary sources Kacprzyk & Zadrożny 2009 and Yager 1982 were not read
    (paywalled; literature.md).
- Protoform 2 "Q R x are S": v = μ_Q(p), with p as above with R (`truth_restricted`), i.e.
  v = μ_Q(Σ_i t(μ_R(x_i), μ_S(x_i)) / Σ_i μ_R(x_i)).
  - Source: hudec2018, Eqs. (7)–(8), §2.3, p. 986, and hudec2022, Eq. (6), p. 325; both
    cite Yager (1982) and Rasmussen & Yager (1997).
  - **The conjunction is applied per record, inside the sum.**
    - hudec2018 Eq. (7) typesets Σ_i (μ_S(x_i) ∧ μ_R(x_i)) / Σ_i μ_R(x_i); checked on the
      rendered page.
    - hudec2022 Eq. (6), by the same first author, typesets Σ μ_P(x_i) ∧ Σ μ_R(x_i) in the
      numerator. We treat that as a typesetting slip: read literally, it ignores which
      records satisfy R.
  - **t-norm.**
    - hudec2018 says the "and operator" is a t-norm (Appendix A); hudec2022 says any t-norm
      can be used and suggests the minimum.
    - Our default `product` and our ablation `min` are both allowed by the sources.
  - **0/0.** Both papers set 0/0 = 0 when no record meets R. We return NaN instead (edge
    cases below), so that "not computable" stays distinguishable from "false".
  - pincay2021 has no restricted protoform in use: it states that restrictions "did not add
    value" (§3.2, p. 172).

**Edge cases (our conventions, not from the sources).**

- Rows with a missing membership (NaN, e.g. the delay of a cancelled train; §1 maps NaN to
  NaN) are dropped row-wise before aggregating, so n counts complete rows only.
- p, and therefore v, is NaN when no complete rows remain or Σ μ_R = 0 (empty
  restriction). NaN is the "not computable" flag; callers test it with `np.isnan`.
- Memberships outside [0, 1] raise `ValueError`.

**Verification.** Invariant I1: analytical cases (all 0, all 1, 80 % fully late, all 0.5,
crisp R) agree to < 1e-9. Invariant I2: memberships agree with Simpful 2.12
`Trapezoidal_MF` to < 1e-6 on 10 000 grid points per word, and truth computed from Simpful
memberships agrees to < 1e-9 (`tests/test_truth_engine.py`). One evaluation over 10⁷ rows
takes about 0.02 s on a laptop.

## 3. Quality measures (UC-022)

Sources, both read in full from the publishers' PDFs (UC-002):
- hudec2018: Hudec, Bednárová & Holzinger, J. Official Statistics 34(4), 2018.
- hudec2022: Hudec, Malovcová, Trumic & Rakovská, Informatica 33(2), 2022.

Page numbers are journal pages. We checked the worked examples below numerically (UC-002
PR). hudec2017, the chapter that introduced the validity-coverage merge, is paywalled. We
cite it only through hudec2018, which states the rule as an equation.

### 3.1 Coverage (summaries with restriction)

Why: a restricted summary can have high validity but rest on a handful of records (outliers).
hudec2022, §3.2, pp. 332–333.

- **Ratio of included records** (hudec2022 Eq. (18), p. 332 = hudec2018 Eq. (A.3), p. 1002):
  i_C = (1/n) Σ_{i=1}^{n} m_i, where m_i = 1 if μ_S(x_i) > 0 and μ_R(x_i) > 0, else 0.
  - n is the number of all records (not only those in R).
  - The paper writes the summarizer as P.
  - m_i is a crisp support count: any membership above 0 counts.
- **Degree of sufficient coverage** (hudec2022 Eq. (19), p. 332, identical to hudec2018
  Eq. (A.4), p. 1002; both attribute it to Wu, Mendel & Joo 2010, wu2010):

  C = f(i_C) =
  - 0 if i_C ≤ r1;
  - 2 (i_C − r1)² / (r2 − r1)² if r1 < i_C < (r1 + r2)/2;
  - 1 − 2 (r2 − i_C)² / (r2 − r1)² if (r1 + r2)/2 ≤ i_C < r2;
  - 1 if i_C ≥ r2.
- **Parameters r1, r2.**
  - hudec2018 (p. 1002) gives **r1 = 0.02 and r2 = 0.15** as "the suggested values".
  - hudec2022 (p. 332) adds that suitable values depend on the length of the summary (the
    number of attributes in R and S). It uses the same values in its worked example (2000
    records; 15 % of the data in the R and S parts counts as fully sufficient coverage).
  - These values are not yet in `config/study.yaml`; see the proposed decision D-027.
- **Worked example** (p. 332, Table 2; UC-022 test vectors). n = 2000, r1 = 0.02, r2 = 0.15:

  | Summary | records with m_i = 1 | i_C | C |
  |---|---|---|---|
  | S1 | 175 | 0.0875 | 0.5377 |
  | S2 | 320 | 0.16 | 1 |
  | S3 | 13 | 0.0065 | 0 |

  The paper says S3 should be excluded even when its validity equals 1.

### 3.2 Quality Qc = validity combined with coverage

- **Rule** (hudec2018 Eq. (9), §2.3, p. 987, attributed there to hudec2017):

  Qc = t(v, C) if C ≥ 0.5; Qc = 0 otherwise.

  - v is the validity of the restricted summary (hudec2018 Eq. (8)) and C the degree of
    sufficient coverage (§3.1).
  - t is a **nonidempotent** t-norm, "for example, a product t-norm".
  - hudec2022 (p. 333) repeats the aggregation by a t-norm, citing hudec2017, without the
    threshold.
- **Config already matches the source.** `mining.coverage_threshold: 0.5` (UC-022
  `c_min = 0.5`) and `mining.tnorm: product` match hudec2018 Eq. (9); no config change is
  needed.
- **Caveat for the min ablation.** min is idempotent, so the `min` ablation of
  `mining.tnorm` is **not** a valid choice for Qc under hudec2018. UC-022 should compute Qc
  with the product t-norm even when the truth ablation uses min (D-027 (2)).
- **Properties for tests.** With the product, Qc ≤ v; Qc = 0 whenever C < 0.5, in
  particular when i_C ≤ r1 (C = 0).
- **Worked examples in hudec2018** (§3.5, p. 997):
  - a summary with v = 0.814 has Qc = 0.8082. With the product this implies C ≈ 0.993; C
    itself is not printed, so this is not an exact test vector.
  - a summary with v = 1 but C = 0 has Qc = 0: "not representative".
- **Mining with Qc.** hudec2018 Eq. (12), §3.1, p. 991, proposes replacing the validity threshold
  of the mining task with Qc(Q, S, R) ≥ u_k, with u_k in (0, 1] (relevant for UC-023 /
  H1c).
- **Discrepancy.** The JOS paper hudec2018 is cited by pincay2021 as "Hudec et al. 2020a,
  JOS 36(4)". The DOI 10.2478/jos-2018-0048 resolves to JOS **34(4), 2018**, pp. 981–1010.
  We cite the DOI version.

### 3.3 Regional quality (summaries per region on a map)

hudec2022, §3.1 (Eqs. (7)–(16), pp. 327–331). The same summary is evaluated in every
region (district) i. The measure relates the region's truth v_i to the region's size.

- **Region proportion** (Eq. (8), p. 327): p_i = N_i / max{N_1, …, N_k}.
  - N_i is the number of records (in the paper: patients) in region i.
  - The maximum is taken over all regions.
- **Rejected simple weighting** (Eq. (7), p. 327): v̄_i = p_i · v_i. The paper shows that it
  suppresses small regions too much and does not adopt it.
- **Adopted measure: ordinal sum** (Eqs. (12)–(15) on p. 330, Eq. (16) on p. 331), with x = v_i, y = p_i,
  split point a = 0.5, and A(x, y) = A1(a ∧ x, a ∧ y) + A2(a ∨ x, a ∨ y) − a (Eq. (13)):
  - A1(x, y) = 2xy on [0, 0.5]², a rescaled product, which behaves conjunctively (Eq. (14));
  - A2(x, y) = −1 + 2x + 2y − 2xy on [0.5, 1]², a rescaled probabilistic sum, which behaves
    disjunctively (Eq. (15));
  - in the mixed regions, the formula reduces to the arithmetic mean form
    AM(x, y) = x + y − 1/2 (Eq. (16)).
- **Rule for v_i = 0.** If v_i = 0, the result is 0 regardless of p_i.
  - It is stated for the uninorm on p. 329 and again for the ordinal sum on p. 331: quality
    measures are only activated when the truth value is greater than 0.
  - Eq. (16) alone would give 0.084 for D3 below, so the rule must be applied explicitly.
- **Restricted summaries.** The maps in the paper (Figs. 9, 11) show the restricted summary
  per district. This implies Eq. (6) per region; the text does not state it explicitly.
- **Worked example** (Table 1 on p. 327 gives cardinalities and truth values; the results
  are on p. 331; three districts with N = 21, 770, 450):

  | District | v_i | p_i | A(v_i, p_i) printed | A recomputed (UC-002) |
  |---|---|---|---|---|
  | D1 | 0.7143 | 0.0273 | 0.2413 | 0.2416 (rounded inputs) |
  | D2 | 0.7013 | 1 | 1 | 1 |
  | D3 | 0 | 0.5844 | 0 | 0 (v_i = 0 rule) |

  The paper also gives A(1, 0.001) = 0.501 (p. 331).
  - Caveat: D2's printed v = 0.7013 equals its proportion 540/770, not μ_most of it; Eq. (4)
    gives about 0.671.
  - D1's v = 0.7143 happens to coincide with its proportion 15/21.
  - Use the (v, p) pairs as given; do not use them to test μ_most.
- **Uninorm alternative.** The paper also discusses a uninorm U_1 (Eq. (9), p. 328;
  Eq. (10), p. 329). It gives 0.0649 for D1 and is unstable near (0, 1), so it was not
  adopted; listed here only for completeness.
- **Interface note.** The measure yields one value per region. The frozen stub
  `regional_quality(per_region_truth, weights) -> float` returns one float; see D-027.

## 4. Summary miner (UC-023)
TODO.

## 5. Assistant decision rule (UC-031)
TODO (UC-031): fuzzy decision rule.

### Crisp official-view baseline (UC-032)

The answer an official punctuality statistic gives for the same question
(`urban_computing.assistant.crisp.crisp_answer`, decision D-026). It ignores the passenger's
margin by design: only crispness and the margin differ from the fuzzy decision (UC-031).

- Rows: REAL arrivals of the question's arriving line (else product) at the hub, in its time
  band and weekday group. Cancelled arrivals and arrivals without a measured delay are not
  counted.
- Hub stops are matched by **identifier**, exactly as for connections (UC-014, data.md §6):
  `stop_id` normalised with the shared stop key (9-digit BPUIC → first 7 digits, child SLOID
  → stop SLOID) against `connections.hub_stop_ids[hub]`, the atlas-resolved ids that the
  caller passes to both the crisp and the fuzzy view, so SRQ2 compares the same arrivals.
  Display names (`stop_name`) are used only as an explicit fallback when no id mapping is
  configured, and the answer then says so.
- p_late = share of those arrivals with delay ≥ 3 min (SBB punctuality rule, D-007;
  `crisp_baseline.punctual_threshold_minutes`).
- Decision (`crisp_baseline.decision_thresholds`): safe if p_late < 0.075, at_risk if
  0.075 ≤ p_late < 0.25, risky if p_late ≥ 0.25. These are the crossover points (μ = 0.5)
  of the fuzzy decision words suggested for UC-031 (safe falls 0.05 → 0.10, at_risk rises
  0.05 → 0.10 and falls 0.20 → 0.30, risky rises 0.20 → 0.30); if UC-031 changes those
  words, these thresholds follow.
- Sentences: "Most … are punctual" if the punctual share is more than half, else "At most half
  of … are punctual" (crisp "most" = more than half, D-012), plus "k of n arrivals were 3 or
  more minutes late".

## 6. Claim checkers (UC-042)

Implementation: `urban_computing.llm.checkers.check(claim, values, vocab, config)` (pure,
no I/O). Each parsed claim "Q [R] x are S" (UC-041, D-022) is scored twice on the same rows:
the segment's values for the summarizer's attribute, restricted crisply by R (time band /
weekday group equal to the claim's key), with missing values (NaN) dropped. The rules are
decision D-023.

**Missing vs cancelled.** NaN means "unknown" (e.g. no measured time) and the row is dropped
by both checkers. A cancelled connection (departing train cancelled, `b_cancelled`) is not
unknown: the passenger lost the connection. Callers therefore encode its slack as −∞, which
both checkers count as `missed` (crisp: −∞ < 0; fuzzy: μ_missed(−∞) = 1, μ_tight =
μ_comfortable = 0) and which stays in n. Example (test): slack [3, 3, 3, −1, −∞, −∞] gives
p(missed) = 0.5 over n = 6; with NaN instead of −∞ it would be 0.25 over n = 4.

**Crisp checker (Stat-to-Text style, D-012).** Each row gets exactly one crisp summarizer
word, then the crisp proportion p = (rows with the word) / (rows) is compared with a crisp
quantifier threshold, set-based as in Eida et al. 2026 (eida2026), but deterministic (no
LLM-written checker; D-012).

Quantifier thresholds (`crisp_baseline` in `config/study.yaml` where present):

| Quantifier | Crisp truth | Source / rationale |
|---|---|---|
| `most` | p > 0.5 | "most" = more than half, Stat-to-Text truth condition (D-012; eida2026 §2.2: most(R, S) iff \|R ∩ S\| > ½\|R\|; `crisp_baseline.most_threshold`). |
| `few` | p < 0.25 | Our choice: Stat-to-Text has no "few". A quarter keeps `few` clearly below `about_half`. |
| `about_half` | \|p − 0.5\| ≤ 0.1 | Our choice (ticket UC-042): within 10 percentage points of one half. |
| `almost_none`, `almost_all` | none (n/a) | Extended words (ablation only, D-022) have no crisp definition; only the fuzzy truth is reported. |

Crisp summarizer words, interval [lo, hi) in minutes. The boundary between neighbouring
words is the crossover of the fuzzy words, (c + d)/2 of the upper word's falling ramp (μ = 0.5
for both words, §1), except where a definition fixes it:

| Attribute | Word | Crisp interval | Boundary rationale |
|---|---|---|---|
| arrival delay | `on_time` | x < 3 | SBB punctuality: < 3 min late is punctual (D-007; `crisp_baseline.punctual_threshold_minutes`). |
| arrival delay | `slightly_late` | 3 ≤ x < 4 | Upper bound 4 = midpoint of the slightly_late → late ramp [3, 5]. |
| arrival delay | `late` | 4 ≤ x < 9 | Upper bound 9 = midpoint of the late → very_late ramp [8, 10]. |
| arrival delay | `very_late` | x ≥ 9 | — |
| connection slack | `missed` | x < 0 | Definition of slack: below 0 the transfer is not possible (§1). |
| connection slack | `tight` | 0 ≤ x < 1.5 | Upper bound 1.5 = midpoint of the tight → comfortable ramp [1, 2]. |
| connection slack | `comfortable` | x ≥ 1.5 | — |

The SBB rule makes `slightly_late` crisply narrow (3–4 min) although its fuzzy word spans
1–5 min; this is the intended contrast between the official and the graded view.

**SRQ3 crisp checker ≠ SRQ2 crisp baseline (by design).** The SRQ2 crisp *baseline* (UC-032,
D-007) is the official view: an arrival is punctual (< 3 min) or not punctual (≥ 3 min), so
"late" there means any delay ≥ 3 min. The SRQ3 crisp *checker* must score claims that use
our four delay words, so it needs one crisp reading *per word*: the 0.5-cut partition above,
where crisp `late` is [4, 9) and a 3-min delay is crisply `slightly_late`. The checker thus
models a Stat-to-Text-style verifier that takes the claim's words literally, while the SRQ2
baseline models the operator's punctuality statistic. Consequence (UC-004 borderline
fixture, Zürich HB IC1: 13 × 3 min, 12 × 0 min): "most trains are late" is crisply *false*
for the checker (0 of 25 rows in [4, 9)), although 52 % are late in the official sense;
"most trains are slightly late" is crisply true (0.52 > 0.5) but fuzzily false
(μ_most(0.52) = 0.057). An ablation with crisp `late` = official ≥ 3 min is UC-054.

**Fuzzy checker.** p_fuzzy is the fuzzy proportion of §2 (crisp R, μ_S from §1) and the truth
is v = μ_Q(p_fuzzy); the claim is fuzzily true if v ≥ 0.5 (`fuzzy_true`).

**Disagreement** (H3c): `crisp_true_fuzzy_false` if crisp is true and v < 0.5,
`crisp_false_fuzzy_true` if crisp is false and v ≥ 0.5, `none` if they agree, `n/a` if either
side is undefined (claim status not ok, word not in the vocabulary, attribute or restriction
column missing, no rows left, extended quantifier). Example (test): 52 % of arrivals fully
late → crisp "most are late" true (0.52 > 0.5), fuzzy truth μ_most(0.52) = 0.06 < 0.5.
