"""Method C, version 2: evidence-grounded graph compilation with a per-assertion ledger.

Five stages, PDF in, graph out, every assertion auditable:

1. Extract. The model reads one document at a time and emits flat claims (entities, attributes,
   relations), each with a verbatim quote (the C v1 reader prompt).
2. Admit. A deterministic gate keeps a claim only if the quote is in the document, the value is in
   the quote, the relation kind is in the task vocabulary and the endpoints are declared. Rejected
   claims go back to the model once with the reasons, then stay rejected.
3. Resolve. Entities are merged across documents by normalized key. Each admitted claim is mapped
   to its ontology construct from a rule table and the SDK schema: class, object-or-facet placement
   and typed range for a property, Relationship node with kind and direction for a relation. A
   relation whose endpoint types do not fit the kind's domain and range is left unresolved, not forced.
4. Compile. Resolved assertions are written with the SDK (GraphWriter over CASEGraph).
5. Gate. The graph is validated with case_validate; if it does not conform, the assertions on the
   violating nodes are quarantined and the graph is compiled again once.

Everything that was not asserted (rejected, unresolved, quarantined, compile errors) is kept in
the ledger with status needs_review instead of being dropped silently. ledger.jsonl has one row per
assertion with its passage, claim, mapping, checks and status; run.json has the counts.

    python harness/pipeline_grounded.py --run-id RUN [--model ollama] [--cases case_01,case_02]
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from graphkit import SCHEMA, RELATION_KINDS, BuildError, GraphWriter, case_validate, expand, iso_time, kb_id
from llm import doc_ids, document_text, main
from pipeline_compiled import KEY, REF_PROPS, REPAIR, TIME_PROPS, TYPES, ask, facet_for, norm_key, parse_claims, verify

ARM = "c_grounded"

# Domain and range of each relation kind, from the task's own description of it.
DOMAIN_RANGE = {
    "Employed_By": ({"Person"}, {"Organization"}),
    "Reports_To": ({"Person"}, {"Person"}),
    "Holds_Account": ({"Person"}, {"EmailAddress", "ApplicationAccount", "Account"}),
    "Owns_Account": ({"Person", "Organization"}, {"Account"}),
    "Located_At": ({"Organization", "Event", "Person"}, {"Location"}),
    "Participated_In": ({"Person"}, {"Event"}),
    "Initiated": ({"Person"}, {"Event"}),
    "Transferred_To": ({"Account"}, {"Account"}),
    "Authorized": ({"Person"}, {"Event"}),
    "Communicated_With": ({"Person"}, {"Person"}),
}
ENTITIES = """You list the entities one investigation document mentions, as JSON. List only what this document states.
Every entity carries a verbatim quote of the sentence that introduces it.

Entity types and what identifies each (the key):
- Person: full name as written
- Organization: name as written (companies, banks)
- Location: the full street address as written, e.g. "12 Main Street, Dayton, OH 45402"
- EmailAddress: the address
- Account: the account number (bank accounts)
- ApplicationAccount: the handle, e.g. "@dreyes"
- Event: the event type as written, e.g. "wire transfer", one entity per distinct event
- EmailMessage: the subject line
- Message: the message text

Reply with one JSON object and nothing else:
{{"entities": [{{"id": "e1", "type": "Person", "key": "...", "quote": "..."}}]}}
List every account number, every event, every email address and every address the document names, each once.

=== Document {doc_id} ({kind}) ===
{text}"""

CLAIMS = """You extract the facts one investigation document states about already-listed entities, as JSON. Extract
only what this document states; do not infer or complete anything. Every claim carries a verbatim quote of the
sentence that states it.

Entities (use these ids only):
{entities}

Attribute properties per type:
{types}
Reference properties point at another entity's id: accountIssuer -> Organization, from/to -> EmailAddress (to may be a list).
Relation kinds (source -> target):
{relations}

Reply with one JSON object and nothing else:
{{"attributes": [{{"entity": "e1", "property": "street", "value": "...", "quote": "..."}}],
 "relations": [{{"source": "e1", "kind": "Employed_By", "target": "e2", "quote": "..."}}]}}
- Do not repeat an entity's key as an attribute.
- Write dates and times as ISO 8601 UTC, e.g. 2025-03-04T10:15:00Z, and quote the sentence that gives them.
- Every relation the document states between listed entities, with the kind's direction as given.

=== Document {doc_id} ({kind}) ===
{text}"""

ADDRESS_RE = re.compile(r"^(.*?),\s*([^,]+?),\s*([A-Z]{2})\s+(\d{5})\s*$")


class Ledger:
    """One row per assertion, from extraction to the graph or the review queue."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, kind: str, doc_id: str, claim: dict, quote: str, status: str, reason: str | None = None,
            mapping: dict | None = None, checks: list[str] | None = None) -> dict:
        row = {"assertion_id": f"a{len(self.rows) + 1}", "kind": kind, "doc_id": doc_id, "claim": claim,
               "quote": quote, "mapping": mapping or {}, "checks": checks or [], "status": status, "reason": reason}
        self.rows.append(row)
        return row

    def counts(self) -> dict:
        return dict(Counter(r["status"] for r in self.rows))

    def write(self, path: Path) -> None:
        path.write_text("\n".join(json.dumps(r, default=str) for r in self.rows) + "\n", encoding="utf-8")


def resolve_entities(per_doc: dict[str, dict], ledger: Ledger) -> tuple[dict[str, str], dict[str, dict]]:
    """Merge entities across documents by type and normalized key; record every merge in the ledger."""
    nodes: dict[str, dict] = {}
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
                nodes[nid] = {"type": e["type"], "key": e["key"], "docs": set(), "rows": []}
            nid = by_key[k]
            merged = bool(nodes[nid]["rows"])  # an earlier mention already created this node
            nodes[nid]["docs"].add(doc_id)
            mapping[f"{doc_id}:{e['id']}"] = nid
            row = ledger.add("entity", doc_id, {"id": e["id"], "type": e["type"], "key": e["key"]}, e["quote"],
                             "resolved", mapping={"node": nid, "class": e["type"], "merged": merged},
                             checks=["quote_in_document", "key_in_quote"])
            nodes[nid]["rows"].append(row)
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
                for row in n["rows"]:
                    row["mapping"]["node"] = full[0]
                    row["checks"].append("first_name_reference_merged")
                nodes[full[0]]["docs"] |= n["docs"]
                nodes[full[0]]["rows"] += n["rows"]
                del nodes[nid]
    return mapping, nodes


def resolve_claims(per_doc: dict[str, dict], mapping: dict[str, str], nodes: dict[str, dict], ledger: Ledger) -> list[dict]:
    """Map every admitted attribute and relation to its ontology construct, or leave it for review."""
    assertions = []
    for doc_id, claims in per_doc.items():
        for a in claims["attributes"]:
            nid = mapping.get(f"{doc_id}:{a['entity']}")
            etype, prop = nodes[nid]["type"], a["property"]
            if prop in REF_PROPS:
                targets = [mapping.get(f"{doc_id}:{t}") for t in a["value"]]
                targets = [t for t in targets if t and nodes[t]["type"] == REF_PROPS[prop]]
                if not targets:
                    ledger.add("attribute", doc_id, a, a["quote"], "needs_review", "reference target is not a resolved entity")
                    continue
                value = targets if prop == "to" else targets[0]
            elif prop in TIME_PROPS:
                value = iso_time(str(a["value"]))
                if not value:
                    ledger.add("attribute", doc_id, a, a["quote"], "needs_review", "time value is not a date-time")
                    continue
            else:
                value = str(a["value"])
            facet = facet_for(etype, prop)
            spec = (SCHEMA[facet] if facet else SCHEMA[etype])["props"].get(prop)
            if spec is None:
                ledger.add("attribute", doc_id, a, a["quote"], "needs_review", f"{etype} has no property {prop} in the ontology")
                continue
            row = ledger.add("attribute", doc_id, a, a["quote"], "resolved",
                             mapping={"node": nid, "class": etype, "facet": facet, "property": spec["key"], "range": spec["range"]},
                             checks=["quote_in_document", "value_in_quote", "property_in_ontology"])
            assertions.append({"row": row, "node": nid, "facet": facet, "prop": prop, "value": value})
        for r in claims["relations"]:
            s, t = mapping.get(f"{doc_id}:{r['source']}"), mapping.get(f"{doc_id}:{r['target']}")
            dom, rng = DOMAIN_RANGE[r["kind"]]
            checks = []
            if (nodes[s]["type"] not in dom or nodes[t]["type"] not in rng) and \
                    nodes[t]["type"] in dom and nodes[s]["type"] in rng:  # stated backwards: the kind fixes the direction
                s, t = t, s
                checks.append("direction_normalized")
            if nodes[s]["type"] not in dom or nodes[t]["type"] not in rng:
                ledger.add("relation", doc_id, r, r["quote"], "needs_review",
                           f"{nodes[s]['type']} {r['kind']} {nodes[t]['type']} does not fit the kind's domain and range "
                           f"({'|'.join(sorted(dom))} -> {'|'.join(sorted(rng))})", mapping={"source": s, "target": t})
                continue
            row = ledger.add("relation", doc_id, r, r["quote"], "resolved",
                             mapping={"source": s, "target": t, "kind": r["kind"], "class": "Relationship", "directional": True},
                             checks=["quote_in_document", "kind_in_vocabulary", "endpoints_declared", "domain_range"] + checks)
            assertions.append({"row": row, "source": s, "target": t, "kind": r["kind"]})
    return assertions


def compile_graph(nodes: dict[str, dict], assertions: list[dict], quarantined: set[str]) -> tuple[GraphWriter, list[tuple[dict, str]]]:
    w = GraphWriter()
    errors: list[tuple[dict, str]] = []
    node_props: dict[str, dict] = {nid: {} for nid in nodes}
    facet_props: dict[tuple, dict] = {}
    for nid, n in nodes.items():
        if n["type"] == "Location":
            m = ADDRESS_RE.match(n["key"].strip())
            if m:
                facet_props.setdefault((nid, "SimpleAddressFacet"), {}).update(
                    street=m.group(1), locality=m.group(2), region=m.group(3), postalCode=m.group(4))
            continue
        kp = KEY.get(n["type"])
        if kp:
            dest = facet_for(n["type"], kp)
            (facet_props.setdefault((nid, dest), {}) if dest else node_props[nid])[kp] = n["key"]
    for a in assertions:
        if a["row"]["assertion_id"] in quarantined or "prop" not in a:
            continue
        bucket = facet_props.setdefault((a["node"], a["facet"]), {}) if a["facet"] else node_props[a["node"]]
        if a["prop"] == "to":
            bucket["to"] = sorted(set(bucket.get("to", [])) | set(a["value"]))
        elif a["prop"] in bucket and a["node"] and nodes[a["node"]]["type"] != "Location":
            a["row"]["checks"].append("later_value_ignored")
        else:
            bucket[a["prop"]] = a["value"]
    for nid, n in nodes.items():
        try:
            w.add_node(nid, n["type"], node_props.get(nid))
        except (BuildError, KeyError, ValueError) as exc:
            for row in n["rows"]:
                errors.append((row, f"node: {exc}"))
    for (nid, facet), props in facet_props.items():
        try:
            w.add_facet(nid, facet, props)
        except (BuildError, KeyError, ValueError) as exc:
            for a in assertions:
                if a.get("node") == nid and a.get("facet") == facet:
                    errors.append((a["row"], f"facet: {exc}"))
    seen = set()
    for a in assertions:
        if "kind" not in a or a["row"]["assertion_id"] in quarantined:
            continue
        if (a["source"], a["kind"], a["target"]) in seen:
            a["row"]["checks"].append("duplicate_of_earlier_assertion")
            continue
        seen.add((a["source"], a["kind"], a["target"]))
        try:
            w.add_relationship(a["source"], a["target"], a["kind"])
        except (BuildError, KeyError, ValueError) as exc:
            errors.append((a["row"], f"relationship: {exc}"))
    return w, errors


def focus_nodes(report: dict, nodes: dict[str, dict]) -> set[str]:
    """Short ids of the graph nodes the validator's report names (case_validate reports text, not rows)."""
    text = json.dumps(report)
    named = set(re.findall(r"http://example\.org/kb/[\w-]+", text))
    return {nid for nid in nodes if expand(kb_id(nid)) in named}


async def run_case(case_dir: Path, out: Path, cfg: dict, llm) -> dict:
    tokens = Counter()
    ledger = Ledger()
    types = "\n".join(f"- {t}: {', '.join(ps)}" for t, ps in TYPES.items())
    relations = "\n".join(f"- {k}: {v}" for k, v in RELATION_KINDS.items())
    per_doc, report = {}, {}
    # 1 + 2: extract and admit, one document at a time
    for doc_id, kind in doc_ids(case_dir).items():
        text = document_text(case_dir, doc_id)
        reply, used = await ask(llm, cfg, ENTITIES.format(doc_id=doc_id, kind=kind, text=text))
        tokens.update(used)
        (out / f"entities_{doc_id}.txt").write_text(reply, encoding="utf-8")
        listed = parse_claims(reply) or {}
        entities = [e for e in (listed.get("entities") or []) if isinstance(e, dict)]
        if not entities:
            report[doc_id] = {"error": "no entities parsed"}
            per_doc[doc_id] = {"entities": [], "attributes": [], "relations": []}
            continue
        roster = "\n".join(f"- {e.get('id')}: {e.get('type')} {json.dumps(str(e.get('key')))}" for e in entities)
        reply, used = await ask(llm, cfg, CLAIMS.format(entities=roster, types=types, relations=relations,
                                                        doc_id=doc_id, kind=kind, text=text))
        tokens.update(used)
        (out / f"claims_{doc_id}.txt").write_text(reply, encoding="utf-8")
        parsed = parse_claims(reply)
        if parsed is None:
            report[doc_id] = {"error": "no parseable JSON"}
            per_doc[doc_id] = {"entities": [], "attributes": [], "relations": []}
            continue
        claims = {"entities": entities, "attributes": parsed.get("attributes") or [], "relations": parsed.get("relations") or []}
        admitted, rejected = verify(claims, text)
        initial, rounds = rejected, 0
        if rejected and cfg["compiled"].get("repair_rounds", 1):
            rounds = 1
            reply, used = await ask(llm, cfg, REPAIR.format(doc_id=doc_id, kind=kind, text=text,
                                                            rejections="\n".join(f"- {r}" for r in rejected[:40])))
            tokens.update(used)
            (out / f"repair_{doc_id}.txt").write_text(reply, encoding="utf-8")
            again = parse_claims(reply)
            if again is not None:
                again.setdefault("entities", claims["entities"])
                admitted2, rejected2 = verify(again, text)
                if sum(map(len, admitted2.values())) >= sum(map(len, admitted.values())) and len(rejected2) <= len(rejected):
                    admitted, rejected = admitted2, rejected2
        for reason in rejected:
            ledger.add("claim", doc_id, {"text": reason}, "", "needs_review", "rejected by the evidence gate: " + reason)
        per_doc[doc_id] = admitted
        report[doc_id] = {"claimed": {k: len(claims.get(k) or []) for k in ("entities", "attributes", "relations")},
                          "admitted": {k: len(v) for k, v in admitted.items()}, "rejected_initial": len(initial),
                          "rejected": len(rejected), "repair_rounds": rounds}
    # 3: resolve
    mapping, nodes = resolve_entities(per_doc, ledger)
    assertions = resolve_claims(per_doc, mapping, nodes, ledger)
    # 4 + 5: compile, gate, quarantine once
    quarantined: set[str] = set()
    gate = []
    writer, errors = compile_graph(nodes, assertions, quarantined)
    for row, msg in errors:
        row["status"], row["reason"] = "needs_review", "compile error: " + msg
    graph = out / "graph.jsonld"
    writer.write(graph)
    (out / "graph_compiled.jsonld").write_text(graph.read_text(encoding="utf-8"), encoding="utf-8")
    validation = case_validate(graph)
    gate.append({"conforms": validation["conforms"], "quarantined": 0})
    if validation["conforms"] is False:
        bad = focus_nodes(validation, nodes)
        for a in assertions:
            if a.get("node") in bad or a.get("source") in bad or a.get("target") in bad:
                quarantined.add(a["row"]["assertion_id"])
                a["row"]["status"], a["row"]["reason"] = "needs_review", "quarantined: its node fails validation"
        if quarantined:
            writer, errors = compile_graph(nodes, assertions, quarantined)
            for row, msg in errors:
                row["status"], row["reason"] = "needs_review", "compile error: " + msg
            writer.write(graph)
            validation = case_validate(graph)
        gate.append({"conforms": validation["conforms"], "quarantined": len(quarantined)})
    for a in assertions:
        if a["row"]["status"] == "resolved":
            a["row"]["status"] = "asserted"
            a["row"]["checks"].append("shacl_conforms" if validation["conforms"] else "shacl_nonconforming")
    for n in nodes.values():
        for row in n["rows"]:
            if row["status"] == "resolved":
                row["status"] = "asserted"
    ledger.write(out / "ledger.jsonl")
    counts = ledger.counts()
    (out / "claims.json").write_text(json.dumps({"per_doc": per_doc, "mapping": mapping,
                                                 "nodes": {k: {"type": v["type"], "key": v["key"], "docs": sorted(v["docs"])}
                                                           for k, v in nodes.items()}}, indent=1))
    return {"status": "empty" if not writer.object_count() else "ok", "tokens": dict(tokens), "documents": report,
            "nodes": len(nodes), "ledger": counts, "review_queue": counts.get("needs_review", 0), "gate": gate,
            "stage_validations": {"compiled": gate[0]["conforms"]}}


if __name__ == "__main__":
    main(ARM, run_case)
