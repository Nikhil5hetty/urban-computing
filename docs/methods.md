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
because that paper shows the curves only graphically (D-008). TODO(verify, UC-002): compare
the breakpoints with the curves in Pincay et al. 2021.

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
- Protoform 1 "Q x are S": v = μ_Q((1/n) Σ μ_S(x_i)) — Pincay et al. 2021 citing
  Kacprzyk & Zadrożny 2009. TODO(verify) equation number.
- Protoform 2 "Q R x are S": v = μ_Q(Σ t(μ_R(x_i), μ_S(x_i)) / Σ μ_R(x_i)). TODO cite.

## 3. Quality measures (UC-022)
TODO: Hudec coverage C and Qc (hudec2017 / hudec2018), regional measure (hudec2022).

## 4. Summary miner (UC-023)
TODO.

## 5. Assistant decision rule (UC-031)
TODO.

## 6. Claim checkers (UC-042)
TODO: crisp truth conditions (eida2026) and fuzzy truth.
