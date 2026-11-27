# Literature

## Status legend

- **verified**: the PM/agent read the cited parts of the source (UC-002, 27 Nov 2026).
- **verified (metadata)**: authors, title, venue, year, pages and DOI checked against the
  publisher, Crossref or OpenAlex; the body was not read (paywalled). Cite such a source
  only for what is stated next to it, e.g. "as attributed by X".
- **to-verify**: do not cite until checked.

## References

| Key | Reference | Use | Status |
|---|---|---|---|
| pincay2021 | Pincay, J., Portmann, E., Terán, L. (2021). Mining Linguistic Summaries in Traffic. IJCCI 2021, Vol. 1: FCTA, SciTePress, 169–176. DOI 10.5220/0010650100003063 (CC BY-NC-ND 4.0) | baseline method; validity Eq. (2) p. 170; β = 0.6 and quantifier curves (Fig. 2) p. 172; future work = quality measures, regions (§5, p. 175) | verified (full text, incl. Fig. 2) |
| pincay2022 | Pincay Nieves, J. (2022). Fuzzifying Geospatial Traffic Data to Convey Information. In *Smart Urban Logistics: Improving Delivery Services by Computational Intelligence*, Fuzzy Management Methods, Springer, 59–87. DOI 10.1007/978-3-031-16704-1_4 | check whether it already adds regions/quality (see below) | verified (metadata); body paywalled, TODO(verify) |
| pincay2026 | Pincay, J., Mancera, J., Walther, J., Terán, L. (2026). From Structured Data to Semantic Insight: A Hybrid ML Framework for Swiss Traffic Safety Analysis. ICEDEG 2026, 419–425 | related Swiss traffic + local LLM work | verified (abstract); DOI not found (not in OpenAlex on 27 Nov 2026) |
| hudec2018 | Hudec, M., Bednárová, E., Holzinger, A. (2018). Augmenting statistical data dissemination by short quantified sentences of natural language. J. Official Statistics 34(4), 981–1010. DOI 10.2478/jos-2018-0048 (open access, CC BY-NC-ND 3.0) | validity Eqs. (5)–(8) p. 986; **Qc = t(v, C) if C ≥ 0.5, else 0**, Eq. (9) p. 987; coverage Eqs. (A.3)–(A.4) with suggested r1 = 0.02, r2 = 0.15, p. 1002 | verified (full text, PDF supplied by Nikhil) |
| hudec2017 | Hudec, M. (2017). Merging Validity and Coverage for Measuring Quality of Data Summaries. In *Information Technology and Computational Physics*, Advances in Intelligent Systems and Computing, Springer, 71–85. DOI 10.1007/978-3-319-44260-0_5 | origin of the validity-coverage merge; cited only as attributed by hudec2018 Eq. (9) and hudec2022 p. 333 | verified (metadata); body paywalled, optional to read |
| hudec2022 | Hudec, M., Malovcová, K., Trumic, R., Rakovská, E. (2022). A New Quality Measure and Visualization of the Short-Quantified Sentences of Natural Language on Maps. Informatica 33(2), 321–342. DOI 10.15388/22-INFOR492 (open access) | validity Eqs. (5)–(6) p. 325; regional ordinal-sum measure Eqs. (7)–(16) pp. 327–331; coverage Eqs. (18)–(19) p. 332 | verified (full text, typeset PDF) |
| wu2010 | Wu, D., Mendel, J. M., Joo, J. (2010). Linguistic summarization using IF-THEN rules. FUZZ-IEEE 2010, 1–8. DOI 10.1109/FUZZY.2010.5584500 | origin of the coverage function f (as attributed by hudec2022) | verified (metadata + abstract) |
| kacprzyk2009 | Kacprzyk, J., Zadrożny, S. (2009). Protoforms of Linguistic Database Summaries as a Human Consistent Tool for Using Natural Language in Data Mining. Int. J. Software Science and Computational Intelligence 1(1), 100–111. DOI 10.4018/jssci.2009010107 | validity formula, as attributed by pincay2021 Eq. (2) | verified (metadata); body paywalled |
| yager1982 | Yager, R. R. (1982). A new approach to the summarization of data. Information Sciences 28(1), 69–86. DOI 10.1016/0020-0255(82)90033-0 | origin of LS; validity as attributed by hudec2022 Eqs. (5)–(6) | verified (metadata); body paywalled |
| eida2026 | Eida, M. M., Anand, G., Singh, A., Maskharashvili, A. (2026). From Tables to Quantified Statements: Evaluating LLM Inference Generation through Executable Verification. arXiv 2609.23966v1 (21 Sep 2026), preprint | crisp checker baseline; "most" = more than half (§2.2); gap: vague quantifiers, graded truth, real data | verified (preprint full text) |
| gaitan2025 | Gaitán-Guerrero, J. F., Martínez-Cruz, C., Espinilla, M., Díaz-Jiménez, D., López, J. L. (2025). A novel fine-tuning and evaluation methodology for large language models on IoT raw data summaries (LLM-RawDMeth): A joint perspective in diabetes care. Computer Methods and Programs in Biomedicine 269, 108878. DOI 10.1016/j.cmpb.2025.108878 | LLMs + fuzzy LS; no truth recomputation of LLM quantifiers | verified |
| wrede2023 | Wrede, C., Winands, M. H. M., Smirnov, E., Wilbik, A. (2023). Towards Explainable Linguistic Summaries. 2023 IEEE Int. Conf. on Fuzzy Systems (FUZZ-IEEE), 1–6. DOI 10.1109/FUZZ52849.2023.10309707 | LS as XAI | verified (abstract + citation page) |
| plenary2022 | Kaczmarek-Majer, K., Casalino, G., Castellano, G., Dominiak, M., Hryniewicz, O., Kamińska, O., Vessio, G., Díaz-Rodríguez, N. (2022). PLENARY: Explaining black-box models in natural language through fuzzy linguistic summaries. Information Sciences 614, 374–399. DOI 10.1016/j.ins.2022.10.010 | LS as XAI | verified (abstract) |
| transportfocus2015 | Transport Focus, Office of Rail and Road (2015). Train punctuality: the passenger perspective. Report, November 2015. https://www.transportfocus.org.uk/?p=4139 | perceived vs official "on time" (passengers expect within one minute) | verified (summary page) |
| spolaor2020 | Spolaor, S., Fuchs, C., Cazzaniga, P., Kaymak, U., Besozzi, D., Nobile, M. S. (2020). Simpful: A User-Friendly Python Library for Fuzzy Logic. Int. J. Computational Intelligence Systems 13(1), 1687–1698. DOI 10.2991/ijcis.d.201012.002 (CC BY-NC 4.0) | library used in pincay2021 and in our invariant I2 | verified |
| spycher2026 | Spycher, J., Portmann, E. (2026). The Limits of Crispness: A Systematic Evaluation and New Perspective for Open Government Data (OGD) Taxonomies. In *Computational Intelligence* (IJCCI 2025), CCIS, Springer, 557–567. DOI 10.1007/978-3-032-15632-7_31 | crisp vs fuzzy framing (Human-IST) | verified (metadata) |
| colombo2024 | Colombo, M. (2024). Phenotropic Interaction: Improving Interfaces with Computing with Words and Perceptions. Fuzzy Management Methods, Springer, Cham. ISBN 978-3-031-42818-0 | CWW in citizen interfaces (Human-IST) | verified (metadata + publisher summary) |
| apertus2025 | Hernández-Cano, A., et al. (Swiss AI Initiative) (2025). Apertus: Democratizing Open and Compliant LLMs for Global Language Environments. arXiv 2509.14233 (also ACL 2026, long paper) | model used (Apertus-8B) | verified (metadata + abstract) |
| zadeh1996 | Zadeh, L. A. (1996). Fuzzy logic = computing with words. IEEE Transactions on Fuzzy Systems 4(2), 103–111. DOI 10.1109/91.493904 | origin of computing with words (words as labels of fuzzy granules) | verified (metadata + abstract, 27 Nov 2026) |
| mendel2010 | Mendel, J. M., Wu, D. (2010). Perceptual Computing: Aiding People in Making Subjective Judgments. Wiley-IEEE Press. DOI 10.1002/9780470599655 | the Perceptual Computer (Per-C) as an architecture for CWW systems; cite for the Per-C by name only | verified (metadata) |
| hevner2004 | Hevner, A. R., March, S. T., Park, J., Ram, S. (2004). Design Science in Information Systems Research. MIS Quarterly 28(1), 75–106. DOI 10.2307/25148625 | design-science framing of the prototype (artefact built and evaluated) | verified (metadata + abstract) |
| bav2026 | Bundesamt für Verkehr BAV (2026). Qualitätsmesssystem im regionalen Personenverkehr (QMS RPV): Analyse der Daten 2025. Bern, May 2026, Aktenzeichen BAV-313.42-1/5/8/4/32. https://www.bav.admin.ch/dam/de/sd-web/EumtSAzzCpCw/qms_rpv_bericht_bav_2025.pdf | official Swiss punctuality definition: a trip is punctual if it arrives less than three minutes after the scheduled time (§1, p. 3), the crisp rule of D-007; applies to all operators in regional passenger transport | verified (definition read) |

## Discrepancy in pincay2021's reference list (UC-002)

pincay2021 (reference list, p. 176) cites the JOS paper as "Hudec, M., Bednárová, E., and
Holzinger, A. (2020a) … JOS, 36(4)". The DOI 10.2478/jos-2018-0048 and the PDF give
**34(4), 2018, pp. 981–1010**. We cite the DOI version (hudec2018).

## Does Pincay (2022) already study regions or quality measures? (UC-002)

**Not determinable from here; provisional answer: regions possibly yes, quality measures no
evidence.**

- The chapter (pincay2022) is paywalled. Its abstract could not be retrieved, and the
  publisher page refused the agent.
- The OpenAlex keyword index for the chapter lists linguistic summarization, probe data of
  delivery vehicles, the Traffic Message Channel, data fusion, imprecise data and Swiss
  Post. None of these is a quality measure (coverage, validity × coverage).
- The closely related IFSA-EUSFLAT 2021 paper "Fuzzifying Geospatial Data to Identify
  Critical Traffic Areas" (DOI 10.2991/asum.k.210827.061) fuzzifies geographical zones
  (geohash) with a type-2 fuzzy system and shows the result on a map. That is a regional
  view, but of traffic criticality, not of summary quality.
- pincay2021 itself names both "combine validity with existing quality measures (Hudec et
  al.)" and "check validity by region, to see whether the data distribution skews the
  summaries" as **future work** (§5, p. 175). So, as of 2021, neither was done in that
  line of work.

**Consequence for SRQ1:** the framing holds unless the chapter computes Hudec's coverage or
regional measure. TODO(verify, Nikhil): open the chapter via the UniFR library (SpringerLink)
and search it for "coverage", "quality" and "region"; record yes/no and the page here.

## What can be reused from Stat-to-Text (eida2026)? (UC-002)

**Code: nothing, for now.** On 27 Nov 2026 the repository named in the paper
(github.com/maimm2/Stat-To-Text) is **empty**: no files, no README and **no licence**.
We checked by cloning it and on the GitHub page. The arXiv paper's footnote says code and
results are released on GitHub but gives no link, and the arXiv record shows no licence.

So:

- **No code may be copied.** Without a licence, default copyright applies.
- **What we reuse is the published method, re-implemented and cited, not copied:**
  - the set-based truth conditions (§2.2), e.g. most(R, S) iff |R ∩ S| > ½|R|, which is our
    D-012 / D-023 crisp checker;
  - the idea of checking each generated quantified statement against the source table
    (§4, step 2).
- **Where we differ:**
  - Our checker is deterministic code, not LLM-written verification functions (D-012).
  - We add graded truth (the fuzzy checker) and real Ist-Daten. Their data is 100
    LLM-generated synthetic tables of 15 rows (§3).
- **Prompts.** Their prompts (Appendix A.1–A.4: table generation, inference generation,
  Python verification prompts) may be described and cited. Do not paste them verbatim into
  our code or paper unless a licence appears.
- **Check again before submission.** If code with a licence appears before the deadline,
  re-check this paragraph (UC-042 / UC-072).
