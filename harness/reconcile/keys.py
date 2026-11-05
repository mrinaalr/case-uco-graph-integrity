"""How an entity is identified and where a value is found in the source: the reconciler's own copy of the rules.

score.py has the same rules for aligning a graph to gold. They are copied, not imported, so that the evaluator and
the method under test share no code: tests/test_keys.py checks that the two agree on the dev documents, so a change
to either side shows as a failing test and not as a hidden advantage. Keys come from profile.toml."""

from __future__ import annotations

import re

from graphkit import PROFILE, iso_time, sentences_of

KEYS: dict[str, list[str]] = {c: list(ks) for c, ks in PROFILE["keys"].items()}
TIME_PROPS = {"startTime", "endTime", "sentTime", "receivedTime"}
CONTAINS_PROPS = {"eventType", "accountType"}  # a type phrase inside the value
NON_MENTION_PROPS = CONTAINS_PROPS - {k for ks in KEYS.values() for k in ks}  # do not place an entity in a sentence
ABBREV = {"st": "street", "ave": "avenue", "rd": "road", "dr": "drive", "blvd": "boulevard", "pkwy": "parkway"}
HONORIFICS = {"mr", "mrs", "ms", "dr", "mx"}
CANON_GROUPS = ("name", "street", "other")
TIME_PATTERNS = [re.compile(p) for p in (
    r"\b[A-Z][a-z]{2}, \d{1,2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} [+-]\d{4}",
    r"\b\d{1,2} [A-Z][a-z]+ \d{4}, \d{2}:\d{2} UTC",
    r"\b[A-Z][a-z]+ \d{1,2}, \d{4} at \d{2}:\d{2} UTC",
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2}| UTC)?",
)]


def norm_text(v: str) -> str:
    return re.sub(r"\s+", " ", str(v)).strip().strip(".,;:'\"").lower()


def norm(p: str, v: str) -> str:
    """A literal in the form two spellings of one value share."""
    if p in TIME_PROPS:
        return iso_time(v) or norm_text(v)
    if p == "name":
        return " ".join(t for t in re.sub(r"[^\w\s]", " ", norm_text(v)).split() if t not in HONORIFICS)
    if p == "street":
        return " ".join(ABBREV.get(t, t) for t in re.sub(r"[^\w\s]", " ", norm_text(v)).split())
    if p in ("addressValue", "accountIdentifier"):
        return norm_text(v).removeprefix("mailto:")
    return norm_text(v)


def norm_kind(kind: str) -> str:
    return re.sub(r"[\s-]+", "_", kind.strip()).lower()


def split_words(v: str) -> str:
    """'AuditReviewStarted' / 'audit_review_started' -> 'audit review started'."""
    return norm_text(re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(v)).replace("_", " "))


def key_of(cls: str, props: dict[str, list[str]]) -> list[str] | None:
    keys = KEYS.get(cls)
    if not keys or not all(props.get(k) for k in keys):
        return None
    return [norm(k, props[k][0]) for k in keys]


def linked_keys(props: dict[str, dict], links: dict[tuple, str]) -> dict[str, dict]:
    """An email account carries the addressValue of the address it links to."""
    out = {k: dict(v) for k, v in props.items()}
    for (s, p), o in links.items():
        if p == "emailAddress" and props.get(o, {}).get("addressValue") and "addressValue" not in out[s]:
            out[s]["addressValue"] = props[o]["addressValue"]
    return out


def canon(group: str, text: str) -> str:
    """The form in which a value and a sentence are compared."""
    if group in ("name", "street"):
        return norm(group, text)
    t = re.sub(r"[^\w\s@.+-]", " ", norm_text(text).removeprefix("mailto:"))
    return " ".join(x for x in (tok.strip(".,-") for tok in t.split()) if x)


def times_in(sentence: str) -> set[str]:
    found = set()
    for pat in TIME_PATTERNS:
        for m in pat.finditer(sentence):
            if iso := iso_time(m.group(0)):
                found.add(iso)
    return found


def index(passages: list[dict]) -> dict:
    """The passages prepared for ground_literal and entity_mentions."""
    sents = [p["text"] for p in passages]
    return {"sents": sents, "doc_of": [p["doc"] for p in passages], "times": [times_in(x) for x in sents],
            "canon": {g: [canon(g, x) for x in sents] for g in CANON_GROUPS}}


def index_text(docs: dict[str, str]) -> dict:
    """The same index from whole documents, split into sentences here."""
    out = []
    for doc, text in docs.items():
        out += [{"doc": doc, "text": s} for s in sentences_of(text)]
    return index(out)


def ground_literal(p: str, value: str, src: dict) -> set[int]:
    """Indices of the passages in which this literal value occurs."""
    if p in TIME_PROPS:
        iso = iso_time(value)
        if not iso:
            return set()
        date_only = len(str(value).strip()) <= 10
        return {i for i, ts in enumerate(src["times"]) if any(t == iso or (date_only and t[:10] == iso[:10]) for t in ts)}
    if p in CONTAINS_PROPS:
        words = set(split_words(value).split())
        return {i for i, x in enumerate(src["canon"]["other"]) if words and words <= set(x.split())}
    group = p if p in ("name", "street") else "other"
    v = canon(group, norm(p, value))
    return {i for i, x in enumerate(src["canon"][group]) if f" {v} " in f" {x} "} if v else set()


def type_phrase_sentences(value: str, src: dict) -> set[int]:
    words = split_words(value).split()
    bigrams = {" ".join(words[i:i + 2]) for i in range(len(words) - 1)}
    return {i for i, x in enumerate(src["canon"]["other"]) if any(f" {b} " in f" {x} " for b in bigrams)}


def entity_mentions(props: dict[str, list[str]], src: dict, cls: str = "") -> dict[str, set]:
    """The passages in which any literal of the entity occurs (IRIs and non-key type classifications aside)."""
    sents = set()
    for p in props.keys() - NON_MENTION_PROPS:
        for v in props[p]:
            if not v.startswith(("http://", "https://")):
                sents |= ground_literal(p, v, src)
                if p in CONTAINS_PROPS or (p == "name" and cls in ("Event", "Action")):
                    sents |= type_phrase_sentences(v, src)
    return {"sents": sents, "docs": {src["doc_of"][i] for i in sents}}


def naming(props: dict, cls: str) -> dict:
    """The literals that place an entity: its key, less any time; every non-time literal for a class with no key."""
    keys = set(KEYS.get(cls, [])) - TIME_PROPS
    return {p: v for p, v in props.items() if (p in keys if keys else p not in TIME_PROPS)}
