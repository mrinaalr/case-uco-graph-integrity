"""Score emitted graphs against gold.

Two scorers share everything but alignment and two rules:

- strict: entities align one-to-one (Hungarian) by similarity of their class
  key properties (e.g. EmailAddress.addressValue), at or above THRESHOLD.
- value: an emitted entity aligns to a class-compatible gold entity when any of
  its literal values matches one of that entity's key values, whatever property
  holds it (Hungarian over the share of keys matched). An eventType matches when
  the normalized gold phrase appears in the emitted value after splitting
  CamelCase and snake_case. A combined address string matches a Location when
  every gold street/city/region/postal value appears in it. Alignment may be
  many-to-one: a second emitted entity matching an already-aligned gold entity is
  a duplicate; its supported triples count, and its other triples are
  duplicate_entity. Communicated_With is symmetric, and AccountFacet.owner
  states the same fact as Owns_Account. A literal whose value
  matches a gold fact on the aligned entity under another property is
  misplaced_property.

Each unsupported triple gets one class, checked in this order: wrong_value,
wrong_relation, wrong_entity, cross_document_conflation, misplaced_property
(value only), invented. A2 triples are traced to the write call that produced
them; A2 is scored at its first validation and at the end.

Grounding is scored separately and without gold: can each emitted assertion
be found in the case's source text? A literal is grounded when its normalized
value occurs in a sentence (times by parsing the text's date spellings, event
and account types by word containment). A relation, or an object property, is
grounded at sentence level when a key literal of each endpoint occurs in one
sentence, at document level when they occur in one document. An entity is
grounded when one of its key literals occurs anywhere. Every emitted assertion
then lands in one cell of grounded x gold-supported; grounded_unsupported is
the traceable claim modeled wrong. Grounding runs against the clean text
(docs/D*.txt, reported) and the PDF-extracted text (docs/D*.pdf.txt); the
number of assertions on which the two disagree is reported. For c_grounded the
ledger's quote-checked assertions are compared with the scorer's grounding.

    python harness/score.py --run-id RUN
    python harness/score.py --self-test     # gold scored against itself
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from graphkit import HARNESS, graph_triples, iso_time, slug

SCORERS = ("strict", "value")
STAGE_ORDER = ["raw", "pass1", "first_validate", "validated", "pass2", "pass3", "pass4", "compiled"]
CLASSES = ["wrong_value", "wrong_relation", "wrong_entity", "cross_document_conflation", "misplaced_property",
           "duplicate_entity", "invented"]
TIME_PROPS = {"startTime", "endTime", "sentTime", "receivedTime"}
KEYS = {"Person": ["name"], "Organization": ["name"], "EmailAddress": ["addressValue"],
        "Account": ["accountIdentifier"], "ApplicationAccount": ["accountIdentifier"], "Location": ["street"],
        "EmailMessage": ["subject", "sentTime"], "Message": ["messageText", "sentTime"],
        "Event": ["eventType", "startTime"], "MessageThread": ["name"],
        "EmailAccount": ["addressValue"]}  # an EmailAccount is keyed by the address it links to
COMPATIBLE = {"Person": {"Identity"}, "Organization": {"Identity"}, "EmailAddress": {"EmailAccount", "ObservableObject"},
              "Account": {"DigitalAccount", "ApplicationAccount", "ObservableObject"},
              "ApplicationAccount": {"Account", "DigitalAccount", "ObservableObject"},
              "EmailMessage": {"Message", "ObservableObject"}, "Message": {"EmailMessage", "ObservableObject"},
              "Event": {"Action"}, "Location": set()}
ANCHOR_PROPS = {"name", "addressValue", "accountIdentifier", "street"}
ABBREV = {"st": "street", "ave": "avenue", "rd": "road", "dr": "drive", "blvd": "boulevard", "pkwy": "parkway"}
HONORIFICS = {"mr", "mrs", "ms", "dr", "mx"}
THRESHOLD = 0.85


def norm_text(v: str) -> str:
    return re.sub(r"\s+", " ", str(v)).strip().strip(".,;:'\"").lower()


def norm(p: str, v: str) -> str:
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


def key_of(cls: str, props: dict[str, list[str]]) -> list[str] | None:
    keys = KEYS.get(cls)
    if not keys or not all(props.get(k) for k in keys):
        return None
    return [norm(k, props[k][0]) for k in keys]


def similarity(a: list[str], b: list[str], cls: str) -> float:
    if len(a) == 2:  # events and messages: the time only breaks ties (e.g. repeated subjects)
        return 0.9 * SequenceMatcher(None, a[0], b[0]).ratio() + 0.1 * (a[1] == b[1])
    return SequenceMatcher(None, a[0], b[0]).ratio()


def split_words(v: str) -> str:
    """'AuditReviewStarted' / 'audit_review_started' -> 'audit review started'."""
    return norm_text(re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(v)).replace("_", " "))


CONTAINS_PROPS = {"eventType", "accountType"}  # value scorer: gold phrase inside the emitted value


def value_matches(gold_prop: str, gold_norm: str, value: str) -> bool:
    """Does an emitted literal carry this (normalized) gold value? eventType/accountType match by containment."""
    if gold_prop in CONTAINS_PROPS:
        return gold_norm in split_words(value)
    return norm(gold_prop, value) == gold_norm


ADDRESS_PROPS = ("street", "locality", "region", "postalCode")


def address_in(gold_props: dict[str, list[str]], value: str) -> bool:
    """A combined address string holds every gold street/city/region/postal value of a Location."""
    if not all(gold_props.get(k) for k in ADDRESS_PROPS):
        return False
    text = f" {norm('street', value)} "
    return all(f" {norm('street', gold_props[k][0])} " in text for k in ADDRESS_PROPS)


# ---- Grounding: is each emitted assertion findable in the source text? (independent of gold) ----

GROUND_SOURCES = {"clean": "D*[0-9].txt", "pdf": "D*.pdf.txt"}
# Literals that do not place an entity in a sentence: type classifications that are not a key
# (accountType "bank account" would place every account in every sentence that says "account").
NON_MENTION_PROPS = CONTAINS_PROPS - {k for ks in KEYS.values() for k in ks}
CANON_GROUPS = ("name", "street", "other")
TIME_PATTERNS = [re.compile(p) for p in (
    r"\b[A-Z][a-z]{2}, \d{1,2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} [+-]\d{4}",   # Sun, 18 May 2025 13:30:00 +0000
    r"\b\d{1,2} [A-Z][a-z]+ \d{4}, \d{2}:\d{2} UTC",                               # 2 May 2025, 09:50 UTC
    r"\b[A-Z][a-z]+ \d{1,2}, \d{4} at \d{2}:\d{2} UTC",                             # May 18, 2025 at 11:30 UTC
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2}| UTC)?",  # ISO 8601, [2025-05-02 10:50 UTC]
)]
GROUND_CELLS = ["grounded_supported", "grounded_unsupported", "ungrounded_supported", "ungrounded_unsupported"]
REL_LEVELS = ["sentence", "document", "indirect", "ungrounded"]


HEADER_LINE = re.compile(r"^(From|To|Cc|Subject|Date):|^[\[@#]")  # mail headers, chat lines: one sentence each


def sentences_of(text: str) -> list[str]:
    """Split a document into sentences. A blank line, a header or chat line, or a line ending in
    . ! ? ends a sentence; any other newline is a wrapped line (PDF-extracted text) and is joined.
    Within a line, . ! ? followed by a capital, quote or bracket ends a sentence."""
    blocks, cur = [], ""
    for line in (x.strip() for x in text.strip().split("\n")):
        if not line:
            blocks, cur = blocks + ([cur] if cur else []), ""
        elif cur and not re.search(r"[.!?]$", cur) and not HEADER_LINE.match(line) and not HEADER_LINE.match(cur):
            cur += " " + line
        elif cur and line[0].islower():
            cur += " " + line
        else:
            blocks, cur = blocks + ([cur] if cur else []), line
    blocks += [cur] if cur else []
    return [x.strip() for b in blocks for x in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(\[@#])", b) if x.strip()]


def canon(group: str, text: str) -> str:
    """The form in which a value and a sentence are compared. 'name' and 'street' use the alignment
    normalizer (punctuation to spaces, honorifics dropped, abbreviations expanded); 'other' lower-cases
    and turns punctuation into spaces except inside tokens such as e-mail addresses."""
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


def load_source(case_dir: Path, pattern: str) -> dict | None:
    files = sorted((case_dir / "docs").glob(pattern))
    if not files:
        return None
    sents, doc_of = [], []
    for f in files:
        for x in sentences_of(f.read_text()):
            sents.append(x)
            doc_of.append(f.name.split(".")[0])
    return {"sents": sents, "doc_of": doc_of, "times": [times_in(x) for x in sents],
            "canon": {g: [canon(g, x) for x in sents] for g in CANON_GROUPS}}


def ground_literal(p: str, value: str, src: dict) -> set[int]:
    """Indices of the source sentences in which this literal value occurs."""
    if p in TIME_PROPS:
        iso = iso_time(value)
        if not iso:
            return set()
        date_only = len(str(value).strip()) <= 10  # a bare date is grounded by any time on that day
        return {i for i, ts in enumerate(src["times"])
                if any(t == iso or (date_only and t[:10] == iso[:10]) for t in ts)}
    if p in CONTAINS_PROPS:  # 'AuditReviewStarted' is grounded by a sentence holding audit, review and started
        words = set(split_words(value).split())
        return {i for i, x in enumerate(src["canon"]["other"]) if words and words <= set(x.split())}
    group = p if p in ("name", "street") else "other"
    v = canon(group, norm(p, value))  # norm first: mailto: and time spellings, as in alignment
    return {i for i, x in enumerate(src["canon"][group]) if f" {v} " in f" {x} "} if v else set()


def entity_mentions(props: dict[str, list[str]], src: dict, cls: str = "") -> dict[str, set]:
    """The sentences in which any literal of the entity occurs (IRIs and non-key type classifications aside)."""
    sents = set()
    for p in props.keys() - NON_MENTION_PROPS:
        for v in props[p]:
            if not v.startswith(("http://", "https://")):
                sents |= ground_literal(p, v, src)
                if p in CONTAINS_PROPS or (p == "name" and cls in ("Event", "Action")):
                    # "RefundRequestInitiation", or an event named "Refund Request Started", is also placed
                    # where "refund request" is; the value scorer aligns such events the same way.
                    sents |= type_phrase_sentences(v, src)
    return {"sents": sents, "docs": {src["doc_of"][i] for i in sents}}


def type_phrase_sentences(value: str, src: dict) -> set[int]:
    """Sentences holding two consecutive words of a type phrase ('invoice submission' for InvoiceSubmissionInitiation)."""
    words = split_words(value).split()
    bigrams = {" ".join(words[i:i + 2]) for i in range(len(words) - 1)}
    return {i for i, x in enumerate(src["canon"]["other"]) if any(f" {b} " in f" {x} " for b in bigrams)}


def ground_relation(s: str, o: str, mentions: dict[str, dict], aliases: dict[str, dict] | None = None) -> str | None:
    ms, mo = mentions.get(s), mentions.get(o)
    if not ms or not mo or not ms["sents"] or not mo["sents"]:
        return None
    if ms["sents"] & mo["sents"]:
        return "sentence"
    if ms["docs"] & mo["docs"]:
        return "document"
    if aliases and ground_relation(s, o, {**mentions, **aliases}) is not None:
        return "indirect"  # a place named by its occupant: "at Ironleaf's office" for the Location Ironleaf is Located_At
    return None


def location_aliases(keyed: dict[str, dict], triples: list[dict], mentions: dict[str, dict]) -> dict[str, dict]:
    """Extended mentions for Locations: the sentences that name an entity the graph places there."""
    out = {}
    for t in triples:
        if not t["lit"] and norm_kind(t["p"]) == "located_at" and keyed.get(t["o"], {}).get("class") == "Location" \
                and t["s"] in mentions and t["o"] in mentions:
            a = out.setdefault(t["o"], {"sents": set(mentions[t["o"]]["sents"]), "docs": set(mentions[t["o"]]["docs"])})
            a["sents"] |= mentions[t["s"]]["sents"]
            a["docs"] |= mentions[t["s"]]["docs"]
    return out


def ground_assertion(t: dict, src: dict, mentions: dict[str, dict], aliases: dict[str, dict]) -> str | None:
    """'sentence' / 'document' / 'indirect' / None for one emitted triple (literal or relation/object property)."""
    if not t["lit"]:
        return ground_relation(t["s"], t["o"], mentions, aliases)
    if ground_literal(t["p"], t["o"], src):
        return "sentence"
    if t["p"] in CONTAINS_PROPS and t["s"] in mentions:
        # A type implied by context, in a sentence that mentions the subject: its head noun ("account
        # 2622357143 at Granite Federal Credit Union" grounds "bank account"), or two consecutive words
        # of it ("the invoice submission was initiated" grounds "InvoiceSubmissionInitiation").
        words = split_words(t["o"]).split()
        head = {words[-1]} if words else set()
        subject_sents = mentions[t["s"]]["sents"]
        if subject_sents & type_phrase_sentences(t["o"], src) or \
                any(f" {h} " in f" {src['canon']['other'][i]} " for i in subject_sents for h in head):
            return "indirect"
    return None


def ground_graph(case_dir: Path, keyed: dict[str, dict], triples: list[dict]) -> dict:
    """Grounding for every (deduplicated) emitted triple and entity, under each source text.
    Returns {"levels": {source: [level per triple]}, "entities": {source: {iri: bool}}}."""
    out = {"levels": {}, "entities": {}}
    for name, pattern in GROUND_SOURCES.items():
        src = load_source(case_dir, pattern)
        if src is None:
            continue
        mentions = {iri: entity_mentions(e["props"], src, e["class"]) for iri, e in keyed.items()}
        aliases = location_aliases(keyed, triples, mentions)
        out["levels"][name] = [ground_assertion(t, src, mentions, aliases) for t in triples]
        out["entities"][name] = {iri: bool(m["sents"]) for iri, m in mentions.items()}
    return out


def ledger_check(run_dir: Path | None, triples: list[dict], grounded: list[bool]) -> dict | None:
    """c_grounded: for each assertion the ledger admitted on its own quote check, what the scorer found.
    Attributes match on (node, property, normalized value); relations on (source, kind, target)."""
    path = run_dir / "ledger.jsonl" if run_dir else None
    if not path or not path.exists():
        return None
    by_key = {}
    for t, g in zip(triples, grounded):
        if t["lit"]:
            key = ("attr", slug(t["s"]), t["p"], norm(t["p"], t["o"]))
        else:
            key = ("rel", slug(t["s"]), norm_kind(t["p"]), slug(t["o"]))
        by_key.setdefault(key, g)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    node_of = {(r["doc_id"], r["claim"]["id"]): r["mapping"]["node"]  # per-document extraction id -> graph node
               for r in rows if r["kind"] == "entity" and r["status"] == "asserted"}
    counts = Counter()
    for row in rows:
        if row["status"] != "asserted" or row["kind"] not in ("attribute", "relation"):
            continue
        m, value = row["mapping"], row["claim"].get("value")
        if row["kind"] == "relation":
            key = ("rel", m["source"], norm_kind(m["kind"]), m["target"])
        elif isinstance(value, list):  # an object property: the value is a reference to another extracted entity
            target = node_of.get((row["doc_id"], value[0])) if value else None
            key = ("rel", m["node"], norm_kind(m["property"].split(":")[-1]), target)
        else:
            p = m["property"].split(":")[-1]
            key = ("attr", m["node"], p, norm(p, str(value)))
        counts["asserted"] += 1
        if key not in by_key:
            counts["not_in_graph"] += 1
        elif by_key[key]:
            counts["scorer_grounded"] += 1
        else:
            counts["scorer_ungrounded"] += 1
    return {k: counts.get(k, 0) for k in ("asserted", "not_in_graph", "scorer_grounded", "scorer_ungrounded")}


def load_gold(case_dir: Path) -> dict:
    gold = json.loads((case_dir / "gold.json").read_text())
    ents = {e["eid"]: e for e in gold["entities"]}
    props: dict[str, dict[str, list[str]]] = {eid: {} for eid in ents}
    triples = {}
    for t in gold["triples"]:
        if t["lit"]:
            props[t["s"]].setdefault(t["p"], []).append(t["o"])
            key = (t["s"], t["p"], norm(t["p"], t["o"]))
        else:
            key = (t["s"], norm_kind(t["p"]) if t["p"][0].isupper() else t["p"], t["o"])
        triples[key] = t
    corpus = " ".join(norm_text(p.read_text()) for p in sorted((case_dir / "docs").glob("D*[0-9].txt")))
    return {"case_id": gold["case_id"], "ents": ents, "props": props, "triples": triples, "corpus": corpus,
            "values": {k[2] for k, t in triples.items() if t["lit"]},
            "keyprops": linked_keys(props, {(t["s"], t["p"]): t["o"] for t in gold["triples"] if not t["lit"]})}


def linked_keys(props: dict[str, dict], links: dict[tuple, str]) -> dict[str, dict]:
    """Props for alignment only: an account carries the addressValue of the address it links to."""
    out = {k: dict(v) for k, v in props.items()}
    for (s, p), o in links.items():
        if p == "emailAddress" and props.get(o, {}).get("addressValue") and "addressValue" not in out[s]:
            out[s]["addressValue"] = props[o]["addressValue"]
    return out


def align(gold: dict, emitted: dict[str, dict]) -> dict[str, str]:
    iris, eids = sorted(emitted), list(gold["ents"])  # sorted: graph order varies by process; ties need a stable order
    if not iris:
        return {}
    scores = np.zeros((len(iris), len(eids)))
    for i, iri in enumerate(iris):
        e = emitted[iri]
        for j, eid in enumerate(eids):
            cls = gold["ents"][eid]["class"]
            if e["class"] != cls and e["class"] not in COMPATIBLE.get(cls, set()):
                continue
            gk, ek = key_of(cls, gold["keyprops"][eid]), key_of(cls, e["props"])
            if gk and ek and (score := similarity(gk, ek, cls)) >= THRESHOLD:
                scores[i, j] = score
    rows, cols = linear_sum_assignment(scores, maximize=True)
    return {iris[i]: eids[j] for i, j in zip(rows, cols) if scores[i, j] >= THRESHOLD}


def align_by_value(gold: dict, emitted: dict[str, dict]) -> tuple[dict[str, str], dict[str, str]]:
    """(primary one-to-one mapping, duplicates mapped many-to-one onto already-aligned gold entities)."""
    iris, eids = sorted(emitted), list(gold["ents"])  # sorted: graph order varies by process; ties need a stable order
    if not iris:
        return {}, {}
    scores = np.zeros((len(iris), len(eids)))
    for i, iri in enumerate(iris):
        e = emitted[iri]
        literals = [v for vs in e["props"].values() for v in vs if not v.startswith(("http://", "https://"))]
        for j, eid in enumerate(eids):
            cls = gold["ents"][eid]["class"]
            if e["class"] != cls and e["class"] not in COMPATIBLE.get(cls, set()):
                continue
            keys = [(k, norm(k, v)) for k in KEYS.get(cls, []) for v in gold["keyprops"][eid].get(k, [])]
            hit = sum(any(value_matches(k, g, v) for v in literals) for k, g in keys)
            if cls == "Location" and any(address_in(gold["props"][eid], v) for v in literals):
                hit = len(keys)
            if hit:
                scores[i, j] = hit / len(keys) + 0.01 * (e["class"] == cls)  # prefer the exact class on ties
    rows, cols = linear_sum_assignment(scores, maximize=True)
    primary = {iris[i]: eids[j] for i, j in zip(rows, cols) if scores[i, j] > 0}
    duplicates = {iri: eids[int(scores[i].argmax())] for i, iri in enumerate(iris)
                  if iri not in primary and scores[i].max() > 0}
    return primary, duplicates


def stage_lookup(run_dir: Path, prov_name: str):
    prov_path, log_path = run_dir / prov_name, run_dir / "log.jsonl"
    prov = json.loads(prov_path.read_text()) if prov_path.exists() else {}
    rows = [json.loads(line) for line in log_path.read_text().splitlines()] if log_path.exists() else []
    stage_of = {"add_node": "write_node", "add_facet": "write_facet", "add_relationship": "write_relationship"}

    def lookup(origin: str):
        idx = prov.get(origin)
        if idx is None or idx >= len(rows):
            return "final_only", None, []
        row = rows[idx]
        return ("repair" if row["after_failed_validation"] else stage_of[row["tool"]]), idx, row["cited_spans"]
    return lookup


def score_case(case_dir: Path, graph: Path | None, run_dir: Path | None = None, prov_name: str | None = None,
               scorer: str = "strict") -> dict:
    gold = load_gold(case_dir)
    n_gold = len(gold["triples"])
    if graph is None or not graph.exists():
        return {"gold_triples": n_gold, "emitted_triples": 0, "supported": 0, "precision": None, "recall": 0.0}
    emitted, raw = graph_triples(graph)
    keyed = {iri: {"class": e["class"], "props": props}
             for (iri, e), props in zip(emitted.items(), linked_keys(
                 {i: e["props"] for i, e in emitted.items()},
                 {(t["s"], t["p"]): t["o"] for t in raw if not t["lit"]}).values())}
    duplicates: dict[str, str] = {}
    if scorer == "value":
        mapping, duplicates = align_by_value(gold, keyed)
    else:
        mapping = align(gold, keyed)
    primary = dict(mapping)
    mapping = {**mapping, **duplicates}
    lookup = stage_lookup(run_dir, prov_name) if prov_name else (lambda o: ("generation", None, []))

    # Emitted entities that carry key literals of more than one gold entity were merged.
    anchors = {}
    for eid, props in gold["props"].items():
        for p in ANCHOR_PROPS & props.keys():
            anchors[(p, norm(p, props[p][0]))] = eid
    merged = {}
    for iri, e in emitted.items():
        hits = {anchors[(p, norm(p, v))] for p, vs in e["props"].items() for v in vs if (p, norm(p, v)) in anchors}
        hits |= {mapping[iri]} if iri in mapping else set()
        if len(hits) > 1:
            merged[iri] = sorted(hits)

    gold_keys = set(gold["triples"])
    linked = {(t["s"], t["o"]) for t in gold["triples"].values() if not t["lit"]}
    seen, supported, unsupported = set(), set(), []
    kept, kept_supported = [], []  # deduplicated emitted triples, in order, and whether gold supports each
    for t in raw:
        if scorer == "value" and not t["lit"] and t["p"] == "owner":  # AccountFacet.owner == owner Owns_Account account
            t = {**t, "s": t["o"], "o": t["s"], "p": "owns_account"}
        is_rel = t["origin"].startswith("rel|")
        p = norm_kind(t["p"]) if is_rel else t["p"]
        s = mapping.get(t["s"])
        o = norm(p, t["o"]) if t["lit"] else mapping.get(t["o"])
        if scorer == "value" and p == "communicated_with" and s and o \
                and (s, p, o) not in gold_keys and (o, p, s) in gold_keys:  # symmetric
            s, o = o, s
        key = (s or t["s"], p, o if (t["lit"] or o) else t["o"])
        if key in seen:
            continue
        seen.add(key)
        kept.append(t)
        if s and (t["lit"] or o) and (s, p, o) in gold_keys:
            supported.add((s, p, o))
            kept_supported.append(True)
            continue
        if scorer == "value" and s and p in CONTAINS_PROPS:
            hit = next((k for k in gold_keys if k[:2] == (s, p) and value_matches(p, k[2], t["o"])), None)
            if hit:
                supported.add(hit)
                kept_supported.append(True)
                continue
        kept_supported.append(False)
        if t["s"] in duplicates or (not t["lit"] and t["o"] in duplicates):
            cls = "duplicate_entity"
        else:
            cls = classify(gold, s, p, o, t, merged, linked, scorer)
        stage, call, cited = lookup(t["origin"])
        unsupported.append({"s": t["s"], "p": t["p"], "o": t["o"], "aligned_s": s, "aligned_o": None if t["lit"] else o,
                            "class": cls, "stage": stage, "call": call, "cited_spans": cited})
    n_emitted = len(seen)
    aligned_classes = [emitted[i]["class"] == gold["ents"][g]["class"] for i, g in primary.items()]

    # Grounding, independent of gold: the same deduplicated triples, under each source text.
    g = ground_graph(case_dir, keyed, kept)
    levels = g["levels"].get("clean", [None] * len(kept))
    grounded = [lv is not None for lv in levels]
    cells = Counter(("grounded" if gr else "ungrounded") + ("_supported" if sup else "_unsupported")
                    for gr, sup in zip(grounded, kept_supported))
    rel_levels = Counter((lv or "ungrounded") for t, lv in zip(kept, levels) if not t["lit"])
    lits = [lv for t, lv in zip(kept, levels) if t["lit"]]
    ents = g["entities"].get("clean", {})
    pdf = g["levels"].get("pdf")
    by_triple = {(t["s"], t["p"], t["o"]): (gr, lv) for t, gr, lv in zip(kept, grounded, levels)}
    for u in unsupported:
        gr, lv = by_triple.get((u["s"], u["p"], u["o"]), (None, None))
        u["grounded"], u["grounding"] = gr, lv
    grounding = {
        "source": "clean", "assertions": len(kept), "grounded": sum(grounded),
        "grounded_rate": sum(grounded) / len(kept) if kept else None,
        "cells": {c: cells.get(c, 0) for c in GROUND_CELLS},
        "literals": {"grounded": sum(lv is not None for lv in lits), "indirect": lits.count("indirect"), "total": len(lits)},
        "relations": {lv: rel_levels.get(lv, 0) for lv in REL_LEVELS},
        "entities": {"grounded": sum(ents.values()), "total": len(ents)},
        "pdf_disagreements": sum((lv is not None) != (pl is not None) for lv, pl in zip(levels, pdf))
        if pdf is not None else None,
        "supported_ungrounded": [{"s": t["s"], "p": t["p"], "o": t["o"]}
                                 for t, gr, sup in zip(kept, grounded, kept_supported) if sup and not gr],
        "ledger": ledger_check(run_dir, kept, grounded),
    }
    return {
        "grounding": grounding,
        "gold_triples": n_gold, "emitted_triples": n_emitted, "supported": len(supported),
        "precision": len(supported) / n_emitted if n_emitted else None,
        "recall": len(supported) / n_gold,
        "alignment": {"gold_entities": len(gold["ents"]), "emitted_entities": len(emitted), "aligned": len(primary),
                      "duplicates": len(duplicates),
                      "gold_aligned_rate": len(primary) / len(gold["ents"]),
                      "emitted_aligned_rate": len(mapping) / len(emitted) if emitted else None,
                      "class_accuracy": sum(aligned_classes) / len(aligned_classes) if aligned_classes else None},
        "merged_entities": merged,
        "unsupported_by_class": dict(Counter(u["class"] for u in unsupported)),
        "unsupported_by_stage": dict(Counter(u["stage"] for u in unsupported)),
        "unsupported": unsupported,
        "missed": sorted(gold["triples"][k]["tid"] for k in gold_keys - supported),
    }


def classify(gold, s, p, o, t, merged, linked, scorer: str = "strict") -> str:
    lit = t["lit"]
    if s is not None and (lit or o is not None):
        if lit and any(gs == s and gp == p for gs, gp, _ in gold["triples"]):
            return "wrong_value"
        if not lit and ((s, o) in linked or (o, s) in linked):
            return "wrong_relation"
        # Gold facts with this property and one endpoint in common: a substitute that appears in the
        # fact's own document is a wrong pick; one only found elsewhere is a conflation.
        in_doc = [gt["doc_id"] in gold["ents"][s if go == o else o]["docs"]
                  for (gs, gp, go), gt in gold["triples"].items()
                  if gp == p and ((go == o and gs != s) or (not lit and gs == s and go != o))]
        if in_doc:
            return "wrong_entity" if any(in_doc) else "cross_document_conflation"
        if t["s"] in merged or (not lit and t["o"] in merged):
            return "cross_document_conflation"
        if not lit and not set(gold["ents"][s]["docs"]) & set(gold["ents"][o]["docs"]):
            return "cross_document_conflation"
        if scorer == "value" and lit and (
                any(gs == s and gt["lit"] and gp != p and value_matches(gp, go, t["o"])
                    for (gs, gp, go), gt in gold["triples"].items())
                or (gold["ents"][s]["class"] == "Location" and address_in(gold["props"][s], t["o"]))):
            return "misplaced_property"
    return "invented"


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


def summarize(arm: str, scorer: str, rows: list[dict]) -> dict:
    failed = [r for r in rows if r["status"] in ("error", "empty")]
    by_class = Counter()
    for r in rows:
        by_class.update(r.get("unsupported_by_class", {}))
    sup, emi, gold = (sum(r[k] for r in rows) for k in ("supported", "emitted_triples", "gold_triples"))
    return {
        "arm": arm, "scorer": scorer, "endpoint": rows[0].get("endpoint"), "model": rows[0].get("model"),
        "sdk_version": rows[0].get("sdk_version"), "cases": len(rows), "failures": len(failed),
        "incomplete": sum(r["status"] == "incomplete" for r in rows),
        "capped": sum(r["status"] == "capped" for r in rows),
        "valid": sum(r.get("final_validation") is True for r in rows),
        "precision_macro": mean(r["precision"] for r in rows if r not in failed),
        "recall_macro": mean(r["recall"] for r in rows),
        "precision_micro": round(sup / emi, 4) if emi else None, "recall_micro": round(sup / gold, 4),
        **{f"unsupported_{c}": by_class.get(c, 0) for c in CLASSES},
        "gold_aligned_rate": mean(r.get("alignment", {}).get("gold_aligned_rate", 0) for r in rows),
        "emitted_aligned_rate": mean(r.get("alignment", {}).get("emitted_aligned_rate") for r in rows),
        **grounding_summary(rows),
        "tokens_prompt": sum(r["tokens"]["prompt"] for r in rows),
        "tokens_completion": sum(r["tokens"]["completion"] for r in rows),
        "wall_s_total": round(sum(r.get("wall_s", 0) for r in rows), 1),
        "wall_s_mean": mean(r.get("wall_s") for r in rows),
        "failed_cases": " ".join(r["case_id"] for r in failed),
    }


def grounding_summary(rows: list[dict]) -> dict:
    """Grounding columns over the cases that produced a graph."""
    gs = [r["grounding"] for r in rows if r.get("grounding")]
    n_assert = sum(g["assertions"] for g in gs)
    cells = Counter()
    for g in gs:
        cells.update(g["cells"])
    unsupported = cells["grounded_unsupported"] + cells["ungrounded_unsupported"]
    rels = Counter()
    for g in gs:
        rels.update(g["relations"])
    n_rel = sum(rels.values())
    ents = sum(g["entities"]["grounded"] for g in gs), sum(g["entities"]["total"] for g in gs)
    ledgers = [g["ledger"] for g in gs if g.get("ledger")]
    ledger = Counter()
    for l in ledgers:
        ledger.update(l)
    return {
        "grounded_rate_micro": round(sum(g["grounded"] for g in gs) / n_assert, 4) if n_assert else None,
        "grounded_rate_macro": mean(g["grounded_rate"] for g in gs),
        **{c: cells.get(c, 0) for c in GROUND_CELLS},
        "grounded_unsupported_share": round(cells["grounded_unsupported"] / unsupported, 4) if unsupported else None,
        "rel_sentence_rate": round(rels["sentence"] / n_rel, 4) if n_rel else None,
        "rel_document_rate": round(rels["document"] / n_rel, 4) if n_rel else None,
        "rel_indirect_rate": round(rels["indirect"] / n_rel, 4) if n_rel else None,
        "entity_grounded_rate": round(ents[0] / ents[1], 4) if ents[1] else None,
        "pdf_disagreements": sum(g["pdf_disagreements"] or 0 for g in gs),
        "ledger_asserted": ledger["asserted"] if ledgers else None,
        "ledger_scorer_ungrounded": ledger["scorer_ungrounded"] if ledgers else None,
        "ledger_not_in_graph": ledger["not_in_graph"] if ledgers else None,
    }


def table(header: list[str], rows: list[list]) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + \
        ["| " + " | ".join(str(x) for x in row) + " |" for row in rows]


def markdown(summaries: list[dict], stage_counts: dict[str, Counter]) -> str:
    cols = ["arm", "scorer", "cases", "failures", "incomplete", "capped", "valid", "precision_macro", "recall_macro",
            "precision_micro", "recall_micro", "tokens_prompt", "tokens_completion", "wall_s_total"]
    first = summaries[0]
    lines = [f"# Faithfulness run\n\nSDK `{first['sdk_version']}`, endpoint `{first['endpoint']}` "
             f"(model `{first['model']}`).\n"]
    lines += table(cols, [[s[c] for c in cols] for s in summaries])
    lines += ["\n## Unsupported triples by class\n"]
    lines += table(["arm", "scorer"] + CLASSES + ["gold_aligned_rate", "emitted_aligned_rate"],
                   [[s["arm"], s["scorer"]] + [s[f"unsupported_{c}"] for c in CLASSES]
                    + [s["gold_aligned_rate"], s["emitted_aligned_rate"]] for s in summaries])
    lines += ["\n## Grounding (independent of gold)\n",
              "Can each emitted assertion be found in the source text? Cells are grounded x gold-supported; "
              "grounded_unsupported is the traceable claim modeled wrong. Relations are grounded at sentence or "
              "document level. pdf_disagreements counts assertions whose grounding differs between the clean and "
              "the PDF-extracted text. ledger_* compares c_grounded's own quote checks with the scorer.\n"]
    gcols = ["grounded_rate_micro"] + GROUND_CELLS + ["grounded_unsupported_share", "rel_sentence_rate",
             "rel_document_rate", "rel_indirect_rate", "entity_grounded_rate", "pdf_disagreements", "ledger_asserted",
             "ledger_scorer_ungrounded", "ledger_not_in_graph"]
    lines += table(["arm", "scorer"] + gcols, [[s["arm"], s["scorer"]] + [s[c] for c in gcols] for s in summaries])
    stages = sorted({k for c in stage_counts.values() for k in c})
    lines += ["\n## Unsupported triples by first stage\n"]
    lines += table(["arm", "scorer"] + stages, [[arm, sc] + [c.get(k, 0) for k in stages] for (arm, sc), c in stage_counts.items()])
    lines += ["\n## Failures (zero recall)\n"] + [f"- {s['arm']}: {s['failed_cases'] or 'none'}"
                                                   for s in summaries if s["scorer"] == "strict"]
    return "\n".join(lines) + "\n"


def variants(arm: str, run_dir: Path) -> list[tuple[str, str, str, str | None]]:
    """(label, graph file, score file, prov file) to score for one case run."""
    if arm == "a2_tools":
        early = "graph_first_validate.jsonld" if (run_dir / "graph_first_validate.jsonld").exists() else "graph.jsonld"
        early_prov = "prov_first_validate.json" if early != "graph.jsonld" else "prov.json"  # never validated: same graph
        return [(f"{arm}@first_validate", early, "score_first_validate.json", early_prov),
                (arm, "graph.jsonld", "score.json", "prov.json")]
    # Any graph_<stage>.jsonld snapshot is scored as <arm>@<stage>: critic passes, the graph before QA, B3's raw reply.
    def order(p: Path):
        stage = p.stem[len("graph_"):]
        return (STAGE_ORDER.index(stage) if stage in STAGE_ORDER else len(STAGE_ORDER),
                int(stage.rsplit("pass", 1)[1]) if stage.startswith("pass") and stage[4:].isdigit() else 0, stage)
    snaps = sorted(run_dir.glob("graph_*.jsonld"), key=order)
    return [(f"{arm}@{p.stem[len('graph_'):]}", p.name, f"score_{p.stem[len('graph_'):]}.json", None) for p in snaps] + [
        (arm, "graph.jsonld", "score.json", None)]


def score_run(run_id: str) -> None:
    run_root = HARNESS / "results" / run_id
    groups: dict[tuple[str, str], list[dict]] = {}
    for arm_dir in sorted(p for p in run_root.iterdir() if p.is_dir()):
        for run_dir in sorted(p for p in arm_dir.iterdir() if p.is_dir()):
            if not (run_dir / "run.json").exists():  # a case still being run
                continue
            meta = json.loads((run_dir / "run.json").read_text())
            data_dir = HARNESS / "data" / run_dir.name
            for label, graph_name, score_name, prov in variants(arm_dir.name, run_dir):
                for scorer in SCORERS:
                    row = dict(meta, arm=label, scorer=scorer)
                    if label.endswith("@first_validate") and meta.get("server_validations"):
                        row["final_validation"] = meta["server_validations"][0]
                    if "@pass" in label and meta.get("pass_validations"):
                        n = int(label.rsplit("pass", 1)[1])
                        row["final_validation"] = (meta["pass_validations"] + [None] * n)[n - 1]
                    elif "@" in label and meta.get("stage_validations"):
                        row["final_validation"] = meta["stage_validations"].get(label.split("@", 1)[1])
                    graph = run_dir / graph_name if meta["status"] not in ("error", "empty") else None
                    try:
                        result = score_case(data_dir, graph, run_dir, prov, scorer)
                    except Exception as exc:  # unparseable output scores as a failure
                        row["status"], row["error"] = "error", f"scoring failed: {exc}"[:2000]
                        result = score_case(data_dir, None)
                    row.update(result)
                    name = score_name if scorer == "strict" else score_name.replace(".json", "_value.json")
                    (run_dir / name).write_text(json.dumps(row, indent=1, default=str))
                    groups.setdefault((label, scorer), []).append(row)
    summaries = [summarize(arm, scorer, rows) for (arm, scorer), rows in groups.items()]
    stage_counts = {arm: sum((Counter(r.get("unsupported_by_stage", {})) for r in rows), Counter())
                    for arm, rows in groups.items()}
    per_case = [{k: r.get(k) for k in ("arm", "scorer", "case_id", "status", "final_validation", "precision", "recall",
                                       "gold_triples", "emitted_triples", "supported", "wall_s")}
                | {"gold_aligned_rate": r.get("alignment", {}).get("gold_aligned_rate"),
                   "emitted_aligned_rate": r.get("alignment", {}).get("emitted_aligned_rate"),
                   "tokens": r["tokens"]["prompt"] + r["tokens"]["completion"],
                   **{c: r.get("unsupported_by_class", {}).get(c, 0) for c in CLASSES},
                   "grounded_rate": (r.get("grounding") or {}).get("grounded_rate"),
                   **{c: (r.get("grounding") or {}).get("cells", {}).get(c) for c in GROUND_CELLS},
                   "pdf_disagreements": (r.get("grounding") or {}).get("pdf_disagreements")}
                for rows in groups.values() for r in rows]
    for name, rows in (("summary.csv", summaries), ("per_case.csv", per_case)):
        with open(run_root / name, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    (run_root / "summary.md").write_text(markdown(summaries, stage_counts))
    print((run_root / "summary.md").read_text())


def self_test() -> None:
    cases = sorted(p for p in (HARNESS / "data").iterdir() if p.is_dir())
    for scorer in SCORERS:
        for case_dir in cases:
            r = score_case(case_dir, case_dir / "gold.jsonld", scorer=scorer)
            assert r["precision"] == 1 and r["recall"] == 1, (scorer, case_dir.name, r["unsupported"][:3], r["missed"][:3])
        print(f"self-test ok ({scorer}): every gold graph scores P=R=1 against itself")
    # Every gold assertion is stated in the documents, so gold must ground completely under both texts.
    rels, pdf_dis = Counter(), 0
    for case_dir in cases:
        r = score_case(case_dir, case_dir / "gold.jsonld")
        g = r["grounding"]
        assert g["grounded"] == g["assertions"], (case_dir.name, g["supported_ungrounded"][:3])
        assert g["entities"]["grounded"] == g["entities"]["total"], (case_dir.name, "ungrounded gold entity")
        assert g["pdf_disagreements"] == 0, (case_dir.name, "clean and PDF text disagree on gold", g["pdf_disagreements"])
        rels.update(g["relations"])
        pdf_dis += g["pdf_disagreements"]
    n_rel = sum(rels.values())
    print(f"self-test ok (grounding): every gold assertion and entity is grounded in its own documents, "
          f"under the clean and the PDF text; {rels['sentence'] / n_rel:.1%} of gold relations at sentence level")
    # And fabrications are not grounded: values absent from case_01, near misses, and a link across documents.
    src = load_source(cases[0], GROUND_SOURCES["clean"])
    assert ground_literal("name", "Luca Petrov", src) and ground_literal("name", "Mr. Luca Petrov", src)
    assert not ground_literal("name", "Luca Petrova", src) and not ground_literal("name", "Zed Quux", src)
    assert ground_literal("accountIdentifier", "3751001456", src) and not ground_literal("accountIdentifier", "37510014561", src)
    assert ground_literal("addressValue", "mailto:luca.petrov@oakhaven.com", src) and not ground_literal("addressValue", "luca@oakhaven.com", src)
    assert ground_literal("startTime", "2025-05-18T11:30:00Z", src) and ground_literal("startTime", "2025-05-18", src)
    assert not ground_literal("startTime", "2025-05-18T11:31:00Z", src) and not ground_literal("startTime", "2025-05-19", src)
    assert ground_literal("eventType", "AuditReviewStarted", src) and not ground_literal("eventType", "WireTransfer", src)
    assert ground_literal("street", "5868 Market St", src) and not ground_literal("street", "5868 Main Street", src)
    assert ground_literal("street", "5868 Market Street, Omaha, NE 68102", src) and not ground_literal("postalCode", "68103", src)
    assert not ground_literal("name", "", src)
    m = {"a": entity_mentions({"name": ["Oscar Banerjee"]}, src), "b": entity_mentions({"name": ["Nadia Moreau"]}, src),
         "c": entity_mentions({"name": ["Luca Petrov"]}, src), "d": entity_mentions({"name": ["Wesley Castillo"]}, src),
         "x": entity_mentions({"name": ["Zed Quux"]}, src)}
    assert ground_relation("d", "c", m) == "sentence"  # "Wesley Castillo's manager is Luca Petrov."
    assert ground_relation("a", "c", m) == "document"  # named on separate lines of the same chat export
    assert ground_relation("a", "b", m) == "document" and ground_relation("a", "x", m) is None
    print("self-test ok (grounding): fabricated values, near misses and unlinked pairs are not grounded")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
    else:
        score_run(args.run_id)


if __name__ == "__main__":
    main()
