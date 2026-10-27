"""Method C: grounded claims, compiled graph.

The model never writes ontology. It reads one document at a time and emits flat claims in a small
task schema: entities (type, key), attributes (entity, property, value) and relations (source,
kind, target), each with a verbatim quote from the document. A deterministic verifier admits a
claim only if the quote is in the document, the value is in the quote, and the relation kind is
in the task vocabulary; rejected claims go back to the reader once, then are dropped. A resolver
merges entities across documents by normalized key, and a compiler writes the CASE/UCO graph with
the SDK (facet placement from the ontology schema, typed literals, Relationship nodes).

    python harness/pipeline_compiled.py --run-id RUN [--model ollama] [--cases case_01,case_02]
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from graphkit import SCHEMA, RELATION_KINDS, BuildError, GraphWriter, iso_time
from llm import doc_ids, document_text, main, tokens_of
from pipeline_monolith import extract_block

ARM = "c_compiled"

# The task schema the reader sees: flat properties per entity type; the compiler places them in facets.
TYPES = {
    "Person": ["name"], "Organization": ["name"],
    "Location": ["street", "locality", "region", "postalCode"],
    "EmailAddress": ["addressValue"],
    "Account": ["accountIdentifier", "accountIssuer", "accountType"],
    "ApplicationAccount": ["accountIdentifier"],
    "Event": ["eventType", "startTime"],
    "EmailMessage": ["from", "to", "subject", "sentTime"],
    "Message": ["from", "to", "messageText", "sentTime"],
}
KEY = {"Person": "name", "Organization": "name", "Location": "street", "EmailAddress": "addressValue", "Account": "accountIdentifier",
       "ApplicationAccount": "accountIdentifier", "Event": "eventType", "EmailMessage": "subject", "Message": "messageText"}
REF_PROPS = {"accountIssuer": "Organization", "from": "EmailAddress", "to": "EmailAddress"}
TIME_PROPS = {"startTime", "sentTime"}
UNQUOTED = {"accountType"}  # values the text implies rather than spells out
ALIASES = {"email": "EmailAddress", "emailaddr": "EmailAddress", "emailaddress": "EmailAddress", "org": "Organization",
           "company": "Organization", "organisation": "Organization", "address": "Location", "place": "Location",
           "bankaccount": "Account", "financialaccount": "Account", "chataccount": "ApplicationAccount",
           "handle": "ApplicationAccount", "email_message": "EmailMessage", "chatmessage": "Message"}

READ = """You extract facts from one investigation document into JSON claims. Extract only what this document states;
do not infer, summarize or complete anything. Every claim carries a verbatim quote of the sentence that states it.

Entity types and their properties:
{types}
Reference properties point at another entity's id: accountIssuer -> Organization, from/to -> EmailAddress (to may be a list).
Relation kinds (source -> target):
{relations}

Reply with one JSON object and nothing else:
{{"entities": [{{"id": "e1", "type": "Person", "key": "full name or address or account number as written", "quote": "..."}}],
 "attributes": [{{"entity": "e1", "property": "street", "value": "...", "quote": "..."}}],
 "relations": [{{"source": "e1", "kind": "Employed_By", "target": "e2", "quote": "..."}}]}}
- key is the entity's identifying value exactly as written (a person's full name, an email address, an account number,
  a full street address for a Location, the event type for an Event, the subject for an EmailMessage, the text for a Message).
- Write dates and times as ISO 8601 UTC, e.g. 2025-03-04T10:15:00Z, and quote the sentence that gives them.
- Do not repeat the key as an attribute; attributes are the other properties listed for the type.

=== Document {doc_id} ({kind}) ===
{text}"""

REPAIR = """Some of your claims for document {doc_id} were rejected by a verifier that checks every quote against the
document text. Return the whole set of claims for this document again, correcting or dropping the rejected ones, in
exactly this JSON shape and nothing else:
{{"entities": [{{"id": "e1", "type": "Person", "key": "...", "quote": "..."}}],
 "attributes": [{{"entity": "e1", "property": "...", "value": "...", "quote": "..."}}],
 "relations": [{{"source": "e1", "kind": "...", "target": "e2", "quote": "..."}}]}}
Every relation endpoint and attribute entity must be an id declared in "entities"; add the missing entities
(accounts, events, email addresses, locations) with their own quotes. Rejections:
{rejections}

=== Document {doc_id} ({kind}) ===
{text}"""


def squash(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def quoted(quote: str, text: str) -> bool:
    q = squash(quote)
    return bool(q) and len(q) >= 8 and q in text


def value_in(value: str, quote: str, prop: str) -> bool:
    v, q = squash(value), squash(quote)
    if prop in TIME_PROPS:
        iso = iso_time(value)
        if not iso:
            return False
        day = iso[:10]
        return day[8:10].lstrip("0") in q or day in q  # the day number or the full date is in the quote
    if prop in UNQUOTED:
        return True
    return v in q or " ".join(t for t in re.sub(r"[^\w\s@.]", " ", v).split()) in re.sub(r"[^\w\s@.]", " ", q)


def verify(claims: dict, text: str) -> tuple[dict, list[str]]:
    """Admit the claims the document supports; list the reasons for every rejection."""
    text = squash(text)
    admitted = {"entities": [], "attributes": [], "relations": []}
    rejected = []
    ids = {}
    for e in claims.get("entities") or []:
        if isinstance(e, dict) and e.get("type") not in TYPES:  # spelling is not grounding: map obvious aliases
            e = {**e, "type": ALIASES.get(str(e.get("type")).lower().replace(" ", ""), e.get("type"))}
        if not isinstance(e, dict) or e.get("type") not in TYPES:
            rejected.append(f"entity {e!r}: unknown type")
            continue
        key = str(e.get("key") or "").strip()
        if not key:
            rejected.append(f"entity {e.get('id')}: no key")
        elif not quoted(str(e.get("quote") or ""), text):
            rejected.append(f"entity {e.get('id')} ({key}): quote not found in the document")
        elif e["type"] != "Message" and not value_in(key, str(e["quote"]), KEY[e["type"]]) and squash(key) not in text:
            rejected.append(f"entity {e.get('id')} ({key}): key not in its quote")
        else:
            admitted["entities"].append({"id": str(e.get("id")), "type": e["type"], "key": key, "quote": e["quote"]})
            ids[str(e.get("id"))] = e["type"]
    for a in claims.get("attributes") or []:
        if not isinstance(a, dict) or str(a.get("entity")) not in ids:
            rejected.append(f"attribute {a.get('entity') if isinstance(a, dict) else a}.{a.get('property') if isinstance(a, dict) else ''}: "
                            f"entity id is not declared in entities")
            continue
        prop, etype = str(a.get("property")), ids[str(a["entity"])]
        if prop not in TYPES[etype]:
            rejected.append(f"attribute {a['entity']}.{prop}: not a property of {etype}")
        elif prop in REF_PROPS:
            targets = a.get("value") if isinstance(a.get("value"), list) else [a.get("value")]
            if all(str(t) in ids and ids[str(t)] == REF_PROPS[prop] for t in targets) \
                    and quoted(str(a.get("quote") or ""), text):
                admitted["attributes"].append({**a, "value": [str(t) for t in targets]})
            else:
                rejected.append(f"attribute {a['entity']}.{prop}: value must be the id of a {REF_PROPS[prop]} entity, with a quote")
        elif not quoted(str(a.get("quote") or ""), text):
            rejected.append(f"attribute {a['entity']}.{prop}={a.get('value')!r}: quote not found in the document")
        elif not value_in(str(a.get("value")), str(a["quote"]), prop):
            rejected.append(f"attribute {a['entity']}.{prop}={a.get('value')!r}: value not in its quote")
        else:
            admitted["attributes"].append(a)
    for r in claims.get("relations") or []:
        if not isinstance(r, dict) or str(r.get("source")) not in ids or str(r.get("target")) not in ids:
            missing = [x for x in (r.get("source"), r.get("target")) if str(x) not in ids] if isinstance(r, dict) else []
            rejected.append(f"relation {r.get('source') if isinstance(r, dict) else r} {r.get('kind') if isinstance(r, dict) else ''} "
                            f"{r.get('target') if isinstance(r, dict) else ''}: endpoint id(s) {missing} are not declared in entities")
        elif r.get("kind") not in RELATION_KINDS:
            rejected.append(f"relation {r.get('kind')!r}: not in the relation vocabulary")
        elif not quoted(str(r.get("quote") or ""), text):
            rejected.append(f"relation {r['source']} {r['kind']} {r['target']}: quote not found in the document")
        else:
            admitted["relations"].append(r)
    return admitted, rejected


def norm_key(etype: str, key: str) -> str:
    k = squash(key)
    if etype in ("Person", "Organization", "Location"):
        k = re.sub(r"[^\w\s@]", " ", k)
        k = " ".join(t for t in k.split() if t not in ("mr", "ms", "mrs", "dr"))
    return k


def resolve(per_doc: dict[str, dict]) -> tuple[dict[str, str], dict[str, dict]]:
    """Map every per-document entity id to one graph node; merge by type and normalized key."""
    nodes: dict[str, dict] = {}   # node id -> {"type", "key"}
    by_key: dict[tuple, str] = {}
    mapping: dict[str, str] = {}
    counter = Counter()
    for doc_id, claims in per_doc.items():
        for e in claims["entities"]:
            k = (e["type"], norm_key(e["type"], e["key"]))
            if k not in by_key:
                counter[e["type"]] += 1
                nid = f"{e['type'].lower()}-{counter[e['type']]}"
                by_key[k] = nid
                nodes[nid] = {"type": e["type"], "key": e["key"], "docs": set()}
            nodes[by_key[k]]["docs"].add(doc_id)
            mapping[f"{doc_id}:{e['id']}"] = by_key[k]
    # A single-token person name that matches exactly one full name is a reference to that person.
    people = {nid: n for nid, n in nodes.items() if n["type"] == "Person"}
    for nid, n in list(people.items()):
        parts = norm_key("Person", n["key"]).split()
        if len(parts) == 1:
            full = [fid for fid, f in people.items() if fid != nid and len(norm_key("Person", f["key"]).split()) > 1
                    and parts[0] in norm_key("Person", f["key"]).split()]
            if len(full) == 1:
                for k, v in mapping.items():
                    if v == nid:
                        mapping[k] = full[0]
                nodes[full[0]]["docs"] |= n["docs"]
                del nodes[nid]
    return mapping, nodes


def facet_for(etype: str, prop: str) -> str | None:
    """Where the ontology carries this property: on the object, or on which facet."""
    if prop in SCHEMA[etype]["props"]:
        return None
    for name in (f"{etype}Facet", "SimpleAddressFacet" if etype == "Location" else None):
        if name and name in SCHEMA and prop in SCHEMA[name]["props"]:
            return name
    for name, spec in SCHEMA.items():
        if spec["is_facet"] and prop in spec["props"]:
            return name
    return None


def compile_graph(per_doc: dict[str, dict], mapping: dict[str, str], nodes: dict[str, dict]) -> tuple[GraphWriter, list[str]]:
    w = GraphWriter()
    errors = []
    node_props: dict[str, dict] = {nid: {} for nid in nodes}
    facet_props: dict[tuple, dict] = {}
    for nid, n in nodes.items():
        kp = KEY[n["type"]] if n["type"] in KEY else None
        if n["type"] == "Location":  # the key is the full address; split it unless parts come as attributes
            m = re.match(r"^(.*?),\s*([^,]+?),\s*([A-Z]{2})\s+(\d{5})\s*$", n["key"].strip())
            if m:
                facet_props.setdefault((nid, "SimpleAddressFacet"), {}).update(
                    street=m.group(1), locality=m.group(2), region=m.group(3), postalCode=m.group(4))
            continue
        if kp:
            dest = facet_for(n["type"], kp)
            (facet_props.setdefault((nid, dest), {}) if dest else node_props[nid])[kp] = n["key"]
    for doc_id, claims in per_doc.items():
        for a in claims["attributes"]:
            nid = mapping.get(f"{doc_id}:{a['entity']}")
            if not nid:
                continue
            etype, prop = nodes[nid]["type"], a["property"]
            value = a["value"]
            if prop in REF_PROPS:
                refs = [mapping.get(f"{doc_id}:{t}") for t in value]
                value = [r for r in refs if r]
                if not value:
                    continue
                value = value if prop == "to" else value[0]
            elif prop in TIME_PROPS:
                value = iso_time(str(value)) or str(value)
            dest = facet_for(etype, prop)
            bucket = facet_props.setdefault((nid, dest), {}) if dest else node_props[nid]
            if prop == "to":
                bucket.setdefault("to", [])
                bucket["to"] = sorted(set(bucket["to"]) | set(value))
            else:
                bucket[prop] = bucket.get(prop) if prop in bucket and etype != "Location" else value  # first value wins
    for nid, n in nodes.items():
        try:
            w.add_node(nid, n["type"], node_props.get(nid))
        except (BuildError, KeyError, ValueError) as exc:
            errors.append(f"node {nid}: {exc}")
    for (nid, facet), props in facet_props.items():
        try:
            w.add_facet(nid, facet, props)
        except (BuildError, KeyError, ValueError) as exc:
            errors.append(f"facet {nid} {facet}: {exc}")
    seen = set()
    for doc_id, claims in per_doc.items():
        for r in claims["relations"]:
            s, t = mapping.get(f"{doc_id}:{r['source']}"), mapping.get(f"{doc_id}:{r['target']}")
            if not s or not t or (s, r["kind"], t) in seen:
                continue
            seen.add((s, r["kind"], t))
            try:
                w.add_relationship(s, t, r["kind"])
            except (BuildError, KeyError, ValueError) as exc:
                errors.append(f"relationship {s} {r['kind']} {t}: {exc}")
    return w, errors


def parse_claims(text: str) -> dict | None:
    block = extract_block(text, "json") or text[text.find("{"): text.rfind("}") + 1]
    try:
        doc = json.loads(block)
    except json.JSONDecodeError:
        return None
    return doc if isinstance(doc, dict) else None


async def ask(llm, cfg: dict, prompt: str) -> tuple[str, dict]:
    resp = await llm.chat.completions.create(
        model=cfg["llm"]["model"], temperature=cfg["llm"]["temperature"], max_tokens=cfg["llm"]["monolith_max_tokens"],
        extra_body=cfg["llm"].get("extra_body"), messages=[{"role": "user", "content": prompt}])
    return resp.choices[0].message.content or "", tokens_of(resp)


async def run_case(case_dir: Path, out: Path, cfg: dict, llm) -> dict:
    tokens = Counter()
    types = "\n".join(f"- {t}: {', '.join(ps)}" for t, ps in TYPES.items())
    relations = "\n".join(f"- {k}: {v}" for k, v in RELATION_KINDS.items())
    per_doc, report = {}, {}
    for doc_id, kind in doc_ids(case_dir).items():
        text = document_text(case_dir, doc_id)
        reply, used = await ask(llm, cfg, READ.format(types=types, relations=relations, doc_id=doc_id, kind=kind, text=text))
        tokens.update(used)
        (out / f"read_{doc_id}.txt").write_text(reply, encoding="utf-8")
        claims = parse_claims(reply)
        if claims is None:
            report[doc_id] = {"error": "no parseable JSON"}
            per_doc[doc_id] = {"entities": [], "attributes": [], "relations": []}
            continue
        admitted, rejected = verify(claims, text)
        rounds = 0
        if rejected and cfg["compiled"].get("repair_rounds", 1):
            rounds = 1
            reply, used = await ask(llm, cfg, REPAIR.format(doc_id=doc_id, kind=kind, text=text,
                                                            rejections="\n".join(f"- {r}" for r in rejected[:40])))
            tokens.update(used)
            (out / f"repair_{doc_id}.txt").write_text(reply, encoding="utf-8")
            again = parse_claims(reply)
            initial = rejected
            if again is not None:
                admitted2, rejected2 = verify(again, text)
                total, total2 = sum(map(len, admitted.values())), sum(map(len, admitted2.values()))
                if total2 >= total and len(rejected2) <= len(rejected):  # the repair must not lose admitted claims
                    admitted, rejected = admitted2, rejected2
        per_doc[doc_id] = admitted
        report[doc_id] = {"claimed": {k: len(claims.get(k) or []) for k in ("entities", "attributes", "relations")},
                          "admitted": {k: len(v) for k, v in admitted.items()}, "rejected": len(rejected),
                          "repair_rounds": rounds, "rejections_initial": (initial if rounds else rejected)[:40],
                          "rejections": rejected[:40]}
    mapping, nodes = resolve(per_doc)
    writer, errors = compile_graph(per_doc, mapping, nodes)
    (out / "claims.json").write_text(json.dumps({"per_doc": per_doc, "mapping": mapping,
                                                 "nodes": {k: {**v, "docs": sorted(v["docs"])} for k, v in nodes.items()},
                                                 "compile_errors": errors}, indent=1))
    writer.write(out / "graph.jsonld")
    status = "empty" if not writer.object_count() else "ok"
    return {"status": status, "tokens": dict(tokens), "documents": report, "nodes": len(nodes),
            "compile_errors": errors[:20]}


if __name__ == "__main__":
    main(ARM, run_case)
