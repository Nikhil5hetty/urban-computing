"""LLM output -> checkable claims (UC-041). Claim is the frozen INTERFACE.

Deterministic: no LLM, no randomness. Rules (ticket UC-041):

1. Prefer the JSON block `{"claims": [{"quantifier", "summarizer", "restriction"}], "text"}`
   and validate each claim against the lexicon.
2. Free text is parsed sentence by sentence with the lexicon (`config/lexicon.yaml`).
3. Anything not mappable becomes a claim with status `unverifiable` (never dropped).
4. Claims with a causal cue become `unverifiable_causal`.

Canonical values: quantifier = vocabulary quantifier word (`most`, `about_half`, ...);
summarizer = `<attribute>:<word>` (`arrival_delay_minutes:late`); restriction =
`family=key` pairs joined by `&` in sorted order (`time_band=morning_peak&weekday_group=monday`)
or None (the question's own segment). Hub and line mentions are not restrictions: they are
the question's segment.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

ClaimStatus = Literal["ok", "unverifiable", "unverifiable_causal", "inconsistent"]
LEXICON_PATH = Path(__file__).resolve().parents[3] / "config" / "lexicon.yaml"


class Claim(BaseModel):
    question_id: str
    slot: int  # k-th claim of the output (pairing key for McNemar, UC-052)
    quantifier: str | None
    summarizer: str | None
    restriction: str | None = None
    status: ClaimStatus = "ok"
    source: Literal["json", "lexicon"] = "json"
    text: str = ""


# ---------------------------------------------------------------------------- lexicon


def load_lexicon(path: Path = LEXICON_PATH) -> dict[str, Any]:
    """Read config/lexicon.yaml (or `path`) into the dict `parse_output` expects."""
    import yaml

    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _norm(text: str) -> str:
    """Lower-case, `_` -> space, curly apostrophe -> ', collapse whitespace."""
    return re.sub(r"\s+", " ", text.replace("_", " ").replace("’", "'")).strip().lower()


def _phrase_regex(phrases: Iterable[str]) -> re.Pattern[str] | None:
    """Whole-word alternation, longest phrase first (regex takes the first alternative)."""
    ps = sorted({_norm(p) for p in phrases if _norm(p)}, key=len, reverse=True)
    if not ps:
        return None
    body = "|".join(re.escape(p).replace(r"\ ", r"\s+") for p in ps)
    return re.compile(rf"(?<![\w-])(?:{body})(?![\w-])", re.IGNORECASE)


@dataclass(frozen=True)
class _Kind:
    regex: re.Pattern[str] | None
    canon: dict[str, str]  # normalised phrase -> canonical value

    def take(self, text: str) -> tuple[list[str], str]:
        """Canonical values found in `text`, and `text` with the matches masked out."""
        if self.regex is None:
            return [], text
        found = [self.canon[_norm(m.group(0))] for m in self.regex.finditer(text)]
        return found, self.regex.sub(" ", text)


@dataclass(frozen=True)
class _Lex:
    summarizers: _Kind
    restrictions: _Kind  # canonical "family=key"
    quantifiers: _Kind
    causal: re.Pattern[str] | None
    negation: re.Pattern[str] | None


def _kind(groups: Mapping[str, Any], canonical_keys_match: bool = True) -> _Kind:
    canon: dict[str, str] = {}
    for value, phrases in groups.items():
        names = [str(p) for p in phrases or []]
        if canonical_keys_match:
            names += [str(value), str(value).split(":")[-1]]
        for p in names:
            canon.setdefault(_norm(p), str(value))
    return _Kind(_phrase_regex(canon), canon)


def _compile(lexicon: Mapping[str, Any]) -> _Lex:
    if not isinstance(lexicon, Mapping):
        raise ValueError("lexicon must be a mapping (see config/lexicon.yaml)")
    for key in ("quantifiers", "summarizers"):
        if not isinstance(lexicon.get(key), Mapping) or not lexicon[key]:
            raise ValueError(f"lexicon needs a non-empty `{key}` section")
    restr: dict[str, list[str]] = {}
    for family, values in (lexicon.get("restrictions") or {}).items():
        for key, phrases in (values or {}).items():
            restr[f"{family}={key}"] = [*(phrases or []), str(key)]
    neg = sorted((_norm(str(p)) for p in lexicon.get("negation_cues") or [] if p), key=len)[::-1]
    neg_body = "|".join(re.escape(p) if p.startswith("n'") else rf"\b{re.escape(p)}\b" for p in neg)
    return _Lex(
        summarizers=_kind(lexicon["summarizers"]),
        restrictions=_kind(restr, canonical_keys_match=False),
        quantifiers=_kind(lexicon["quantifiers"]),
        causal=_phrase_regex(lexicon.get("causal_cues") or []),
        negation=re.compile(neg_body, re.IGNORECASE) if neg_body else None,
    )


@lru_cache(maxsize=8)
def _compile_cached(key: str) -> _Lex:
    return _compile(json.loads(key))


def _lex(lexicon: Mapping[str, Any]) -> _Lex:
    if not isinstance(lexicon, Mapping):
        raise ValueError("lexicon must be a mapping (see config/lexicon.yaml)")
    return _compile_cached(json.dumps(lexicon, sort_keys=True, default=str))


# ---------------------------------------------------------------------------- matching

_PROPORTION = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:%|percent\b|per\s+cent\b)|\b\d+\s+(?:in|out\s+of)\s+\d+\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _Scan:
    quantifiers: list[str]
    summarizers: list[str]
    restrictions: list[str]
    causal: bool
    negated: bool
    numeric: bool


def _scan(lex: _Lex, text: str) -> _Scan:
    """Find phrases in the order summarizer -> restriction -> quantifier, masking each match
    so that e.g. "a few minutes late" is not also read as the quantifier "a few"."""
    t = f" {text} "
    causal = bool(lex.causal and lex.causal.search(t))
    summ, t = lex.summarizers.take(t)
    restr, t = lex.restrictions.take(t)
    quant, t = lex.quantifiers.take(t)
    numeric = bool(_PROPORTION.search(t))
    negated = bool(lex.negation and lex.negation.search(_norm(t)))
    return _Scan(quant, summ, restr, causal, negated, numeric)


def _restriction(values: Iterable[str]) -> tuple[str | None, bool]:
    """Join `family=key` values; ok=False if one family gets two different keys."""
    pairs = sorted(set(values))
    families = [p.split("=", 1)[0] for p in pairs]
    if len(families) != len(set(families)):
        return None, False
    return ("&".join(pairs) or None), True


def _one(values: list[str]) -> str | None:
    distinct = list(dict.fromkeys(values))
    return distinct[0] if len(distinct) == 1 else None


def _status(causal: bool, checkable: bool) -> ClaimStatus:
    if causal:
        return "unverifiable_causal"
    return "ok" if checkable else "unverifiable"


# ---------------------------------------------------------------------------- free text

_SENTENCE_END = re.compile(r"(?<=[.!?;])\s+|\n+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text or "") if s and s.strip()]


def _claim_from_sentence(lex: _Lex, qid: str, sentence: str) -> Claim | None:
    """One sentence -> a claim, or None if the sentence makes no quantified statement."""
    p = _scan(lex, sentence)
    if not (p.quantifiers or p.summarizers or p.causal or p.numeric):
        return None  # e.g. "Have a good trip." - nothing to check
    restriction, r_ok = _restriction(p.restrictions)
    q, s = _one(p.quantifiers), _one(p.summarizers)
    return Claim(
        question_id=qid,
        slot=0,
        quantifier=q,
        summarizer=s,
        restriction=restriction,
        status=_status(p.causal, bool(q and s and r_ok and not p.negated)),
        source="lexicon",
        text=sentence,
    )


def _lexicon_claims(lex: _Lex, qid: str, text: str) -> list[Claim]:
    claims = (_claim_from_sentence(lex, qid, s) for s in _sentences(text))
    return [c for c in claims if c is not None]


# ---------------------------------------------------------------------------- JSON


def _find_json(raw: str) -> tuple[dict[str, Any] | None, str]:
    """First JSON object with a `claims` key; returns (object, raw text without it)."""
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", raw):
        try:
            obj, end = dec.raw_decode(raw, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "claims" in obj:
            outside = re.sub(r"```(?:json)?", " ", raw[: m.start()] + " " + raw[end:])
            return obj, outside
    return None, raw


def _json_word(kind: _Kind, value: Any) -> str | None:
    """JSON field -> canonical value: exact phrase, else exactly one phrase inside it."""
    if not isinstance(value, str) or not value.strip():
        return None
    v = _norm(value)
    if v in kind.canon:
        return kind.canon[v]
    found, _ = kind.take(f" {v} ")
    return _one(found)


def _json_restriction(lex: _Lex, value: Any) -> tuple[str | None, bool]:
    """JSON restriction -> canonical string; ok=False if (part of) it cannot be mapped."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, True
    if not isinstance(value, str):
        return None, False
    v = value.strip()
    if re.fullmatch(r"[a-z_]+=[a-z_]+(?:&[a-z_]+=[a-z_]+)*", v):  # already canonical
        parts = v.split("&")
        if not set(parts) <= set(lex.restrictions.canon.values()):
            return None, False
        return _restriction(parts)
    found, rest = lex.restrictions.take(f" {_norm(v)} ")
    leftover = re.sub(r"\b(?:and|on|in|at|the|during|of)\b|[^a-z]", "", rest)
    if not found or leftover:
        return None, False
    return _restriction(found)


def _json_claims(lex: _Lex, qid: str, obj: dict[str, Any]) -> list[Claim] | None:
    """Validated JSON claims; None if the block does not follow the schema at all."""
    items = obj.get("claims")
    if not isinstance(items, list):
        return None
    out: list[Claim] = []
    for item in items:
        text = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if not isinstance(item, dict):
            out.append(
                Claim(question_id=qid, slot=0, quantifier=None, summarizer=None,
                      status="unverifiable", source="json", text=text)
            )  # fmt: skip
            continue
        q = _json_word(lex.quantifiers, item.get("quantifier"))
        s = _json_word(lex.summarizers, item.get("summarizer"))
        r, r_ok = _json_restriction(lex, item.get("restriction"))
        fields = " ".join(
            str(item.get(k) or "") for k in ("quantifier", "summarizer", "restriction")
        )
        causal = bool(lex.causal and lex.causal.search(f" {fields} "))
        out.append(
            Claim(question_id=qid, slot=0, quantifier=q, summarizer=s, restriction=r,
                  status=_status(causal, bool(q and s and r_ok)), source="json", text=text)
        )  # fmt: skip
    return out


def _merge(json_claims: list[Claim], text_claims: list[Claim]) -> list[Claim]:
    """JSON claims first; add free-text claims the JSON does not already state. A free-text
    claim with another quantifier for the same summarizer + restriction contradicts the
    JSON: both are kept and marked `inconsistent`."""
    claims = list(json_claims)
    stated = {(c.quantifier, c.summarizer, c.restriction) for c in json_claims if c.status == "ok"}
    seen: set[tuple[Any, ...]] = set()
    for tc in text_claims:
        key = (tc.quantifier, tc.summarizer, tc.restriction, tc.status, tc.text)
        if (tc.status == "ok" and key[:3] in stated) or key in seen:
            continue  # restates a JSON claim, or JSON "text" repeated outside the block
        seen.add(key)
        if tc.status == "ok":
            clash = [
                i
                for i, j in enumerate(claims)
                if j.source == "json"
                and j.status in ("ok", "inconsistent")
                and (j.summarizer, j.restriction) == (tc.summarizer, tc.restriction)
                and j.quantifier != tc.quantifier
            ]
            for i in clash:
                claims[i] = claims[i].model_copy(update={"status": "inconsistent"})
            if clash:
                tc = tc.model_copy(update={"status": "inconsistent"})
        claims.append(tc)
    return claims


# ---------------------------------------------------------------------------- public


def parse_output(question_id: str, raw: str, lexicon: dict) -> list[Claim]:
    """Parse JSON block first, lexicon fallback; never drops a claim.

    Inputs: question id, raw LLM output, lexicon dict (`load_lexicon()`).
    Returns claims with `slot` 0..k-1: the JSON claims in their order, then free-text
    claims the JSON does not already state (see `_merge` for `inconsistent`). Without a
    valid JSON block all claims come from the free text: the whole output if there is no
    block, else the text outside it plus its "text" field (if `claims` is not a list).
    Sentences without any quantifier, summarizer, proportion or causal cue are not claims.
    Raises ValueError on a malformed lexicon.
    """
    lex = _lex(lexicon)
    raw = raw or ""
    obj, outside = _find_json(raw)
    if obj is None:
        claims = _lexicon_claims(lex, question_id, raw)
    else:
        json_text = obj.get("text") if isinstance(obj.get("text"), str) else ""
        free = "\n".join(t for t in (outside, json_text) if t and t.strip())
        json_claims = _json_claims(lex, question_id, obj)
        text_claims = _lexicon_claims(lex, question_id, free)
        # invalid schema: only the text outside the block (+ its "text") is parsed
        claims = text_claims if json_claims is None else _merge(json_claims, text_claims)
    return [c.model_copy(update={"slot": k}) for k, c in enumerate(claims)]


def claim_stats(claims: Iterable[Claim]) -> dict[str, float]:
    """Counts per status and the unverifiable rate, over one or many outputs.

    Returns {"n", "ok", "unverifiable", "unverifiable_causal", "inconsistent",
    "unverifiable_rate"}; rate = (unverifiable + unverifiable_causal) / n, NaN if n = 0.
    """
    cs = list(claims)
    out: dict[str, float] = {"n": float(len(cs))}
    for s in ("ok", "unverifiable", "unverifiable_causal", "inconsistent"):
        out[s] = float(sum(1 for c in cs if c.status == s))
    unv = out["unverifiable"] + out["unverifiable_causal"]
    out["unverifiable_rate"] = unv / len(cs) if cs else math.nan
    return out
