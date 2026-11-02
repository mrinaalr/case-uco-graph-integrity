"""Arm C: EDC (Extract, Define, Canonicalize; Zhang and Soh 2024) as shipped, canonicalizing to the CASE/UCO
target schema.

EDC is the edc/ submodule (clear-nus/edc, 02aad17), run in its README's target-alignment setting with its default
prompt templates and few-shot examples, no refinement and no schema enrichment. EDC takes one text per input
line and leaves chunking to its user, so each sentence of the PDFs (llm.passages) is one input. Not changed:
EDC's prompts, parsing, temperature, max_tokens and canonicalization logic. Adapted:

- LLM calls go to the harness endpoint, the base model every arm uses. EDC sends only models named "gpt" to its
  OpenAI client, so that check returns true; an empty reply is returned as " " (no choice) because EDC reads its
  first character.
- Two fixes, counted and disclosed. edc_framework.py:270 raised UnboundLocalError on any run whose first input
  has no triples (about 12 of 100 cases); it is loaded with that one line fixed (patched_framework). The base model
  often replies with tuples, which EDC's parser drops whole (22% of sentences); they are rewritten as lists first
  (as_lists; run.json counts them).
- EDC's default embedder, intfloat/e5-mistral-7b-instruct (14 GB), does not fit this machine; the hook's pinned
  embedder is used ([hook] in config.toml; EDC takes any sentence transformer). edc.utils.e5_mistral_utils, the
  schema-retriever training module, is stubbed: it imports packages EDC does not call in this setting.
- The target schema is CASE/UCO in the task's terms: the ten relation kinds, and Class.property for each property
  of the task classes below, defined from the SDK registry.

EDC returns string triples and does not type entities. The serializer types each entity string by the domain and
range of the relations it appears in (most votes; ties go to the first), treats identical strings as one entity,
and writes the graph with the SDK (facet placement from the ontology schema, typed literals, Relationship nodes).
A property whose subject is typed as another class is dropped. Each entity string is also written as the entity's
key property (name, addressValue, ...). The classes, and the key literals no EDC triple states, are the adapter's
own edges: adapter_edges.json lists them, and score.py scores c_edc with and without them (@no_adapter).

    python harness/pipeline_edc.py --run-id RUN [--model tinker] [--cases case_01,case_02]
"""

from __future__ import annotations

import ast
import csv
import json
import re
import shutil
import sys
import types
from collections import Counter
from pathlib import Path

from huggingface_hub import snapshot_download
from openai import OpenAI

from graphkit import (REPO, RELATION_KINDS, RELATION_PHRASES, SCHEMA, BuildError, GraphWriter, expand, iso_time,
                      kb_id, property_definition, words)
from llm import main, passages, tokens_of

ARM = "c_edc"
EDC_DIR = REPO / "edc"

# The task classes and the properties the serializer places; the compiler puts them on the object or its facet.
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
# Domain and range of each kind, the first class where the task vocabulary allows two.
KIND_TYPES = {"Employed_By": ("Person", "Organization"), "Reports_To": ("Person", "Person"),
              "Holds_Account": ("Person", "EmailAddress"), "Owns_Account": ("Person", "Account"),
              "Located_At": ("Organization", "Location"), "Participated_In": ("Person", "Event"),
              "Initiated": ("Person", "Event"), "Transferred_To": ("Account", "Account"),
              "Authorized": ("Person", "Event"), "Communicated_With": ("Person", "Person")}


def target_schema() -> dict[str, tuple[str, str | None, str]]:
    """relation -> (domain, range or None for a literal, definition) in EDC's 'subject entity / object entity' style."""
    out = {k: (d, r, f"The subject entity {RELATION_PHRASES[k]} the object entity ({RELATION_KINDS[k]}).")
           for k, (d, r) in KIND_TYPES.items()}
    for cls, props in TYPES.items():
        for p in props:
            out[f"{cls}.{p}"] = (cls, REF_PROPS.get(p), f"The object entity is the {words(p)} of the subject entity, "
                                                          f"{'an' if cls[0] in 'AEIOU' else 'a'} {words(cls)}: "
                                                          f"{property_definition(cls, p)}.")
    return out


SCHEMA_EDC = target_schema()
USAGE: Counter = Counter()
CALLS: list[dict] = []  # every LLM reply of the current case, kept in llm_calls.jsonl
TUPLE_REPLIES: Counter = Counter()  # replies rewritten from tuples to lists, per case
_EDC = None
CRASH = 'logger.debug(f"Retrieved candidate relations {canon_candidate_dict}")'  # edc_framework.py:270
FIX = 'logger.debug(f"Retrieved candidate relations {canon_candidate_dict_list}")'


def patched_framework() -> types.ModuleType:
    """edc.edc_framework with one line fixed. Line 270 logs canon_candidate_dict, which is unset when the first
    input has no triples, so the whole run raised UnboundLocalError; it logs the input's candidate list instead."""
    path = EDC_DIR / "edc" / "edc_framework.py"
    source = path.read_text()
    assert source.count(CRASH) == 1, f"{path} is not the pinned 02aad17 version"
    module = types.ModuleType("edc.edc_framework")
    module.__file__ = str(path)
    sys.modules["edc.edc_framework"] = module
    exec(compile(source.replace(CRASH, FIX), str(path), "exec"), module.__dict__)
    return module


def as_lists(raw: str) -> str:
    """A reply written as tuples, "[('a', 'b', 'c'), ...]", rewritten as lists: EDC's parser reads only [...]
    triples and drops the whole reply otherwise. Any other reply is unchanged."""
    try:
        value = ast.literal_eval(raw[raw.index("["): raw.rindex("]") + 1])
    except (ValueError, SyntaxError, TypeError):
        return raw
    if not isinstance(value, list) or not any(isinstance(t, tuple) for t in value):
        return raw
    TUPLE_REPLIES["converted"] += 1
    return repr([list(t) if isinstance(t, tuple) else t for t in value])


def framework(cfg: dict, arm_dir: Path):
    """EDC once per process, its LLM calls sent to the harness endpoint."""
    global _EDC
    if _EDC is not None:
        return _EDC
    sys.path.insert(0, str(EDC_DIR))
    sys.modules["edc.utils.e5_mistral_utils"] = types.SimpleNamespace(MistralForSequenceEmbedding=None)
    import edc.utils.llm_utils as llm_utils
    EDC = patched_framework().EDC
    parse = llm_utils.parse_raw_triplets
    llm_utils.parse_raw_triplets = lambda raw: parse(as_lists(raw))

    llm = cfg["llm"]
    client = OpenAI(base_url=llm["base_url"], api_key=llm["api_key"] or "none", timeout=llm.get("request_timeout_s", 600))

    def complete(model, system_prompt, history, temperature=0, max_tokens=512):
        messages = ([{"role": "system", "content": system_prompt}] if system_prompt is not None else []) + history
        resp = client.chat.completions.create(model=llm["model"], messages=messages, temperature=temperature,
                                              max_tokens=max_tokens, extra_body=llm.get("extra_body"))
        USAGE.update(tokens_of(resp))
        CALLS.append({"max_tokens": max_tokens, "prompt": messages[-1]["content"][-300:], "reply": resp.choices[0].message.content})
        return resp.choices[0].message.content or " "

    llm_utils.is_model_openai = lambda name: True
    llm_utils.openai_chat_completion = complete
    schema_csv = arm_dir / "target_schema.csv"
    with open(schema_csv, "w", newline="") as fh:
        csv.writer(fh).writerows((rel, d) for rel, (_, _, d) in SCHEMA_EDC.items())
    embedder = snapshot_download(cfg["hook"]["embed_model"], revision=cfg["hook"]["embed_revision"],
                                 allow_patterns=["*.json", "*.txt", "model.safetensors"])  # what SentenceTransformer loads
    t, f = EDC_DIR / "prompt_templates", EDC_DIR / "few_shot_examples" / "example"  # run.py's defaults
    _EDC = EDC(oie_llm=llm["model"], oie_prompt_template_file_path=t / "oie_template.txt",
               oie_few_shot_example_file_path=f / "oie_few_shot_examples.txt",
               sd_llm=llm["model"], sd_prompt_template_file_path=t / "sd_template.txt",
               sd_few_shot_example_file_path=f / "sd_few_shot_examples.txt",
               sc_llm=llm["model"], sc_embedder=embedder, sc_prompt_template_file_path=t / "sc_template.txt",
               sr_adapter_path=None, sr_embedder=embedder, oie_refine_prompt_template_file_path=t / "oie_r_template.txt",
               oie_refine_few_shot_example_file_path=f / "oie_few_shot_refine_examples.txt",
               ee_llm=llm["model"], ee_prompt_template_file_path=t / "ee_template.txt",
               ee_few_shot_example_file_path=f / "ee_few_shot_examples.txt", em_prompt_template_file_path=t / "em_template.txt",
               target_schema_path=schema_csv, enrich_schema=False, loglevel=None)
    return _EDC


def clean(entity: str) -> str:
    """An EDC entity string as a value: its few-shot examples write entities WebNLG-style ('Luca_Petrov', '"x"')."""
    s = str(entity).strip().strip('"').strip()
    return s if "@" in s else s.replace("_", " ")


def claims_of(triples: list[list[str]]) -> tuple[dict, dict[str, str], dict[str, dict]]:
    """EDC's triples as compiler claims, entity strings typed by the relations they appear in."""
    votes: dict[str, Counter] = {}
    for s, r, o in triples:
        domain, rng, _ = SCHEMA_EDC[r]
        votes.setdefault(clean(s), Counter())[domain] += 1
        if rng:
            votes.setdefault(clean(o), Counter())[rng] += 1
    typed = {e: c.most_common(1)[0][0] for e, c in votes.items()}  # most_common keeps first-seen order on ties
    claims = {"entities": [], "attributes": [], "relations": []}
    for s, r, o in triples:
        s, o = clean(s), clean(o)
        if r in KIND_TYPES:
            claims["relations"].append({"source": s, "kind": r, "target": o})
        elif typed[s] == r.split(".")[0]:
            prop = r.split(".")[1]
            claims["attributes"].append({"entity": s, "property": prop, "value": [o] if prop in REF_PROPS else o})
    counter, mapping, nodes = Counter(), {}, {}
    for e, cls in typed.items():
        counter[cls] += 1
        nid = f"{cls.lower()}-{counter[cls]}"
        mapping[f"edc:{e}"] = nid
        nodes[nid] = {"type": cls, "key": e}
    return claims, mapping, nodes


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


def compile_graph(per_doc: dict[str, dict], mapping: dict[str, str], nodes: dict[str, dict]
                  ) -> tuple[GraphWriter, list[str], list[tuple]]:
    """Also returns the (node, property, value) key literals written from the entity strings."""
    w = GraphWriter()
    errors, keyed = [], []
    node_props: dict[str, dict] = {nid: {} for nid in nodes}
    facet_props: dict[tuple, dict] = {}
    for nid, n in nodes.items():
        kp = KEY[n["type"]] if n["type"] in KEY else None
        if n["type"] == "Location":  # the key is the full address; split it unless parts come as attributes
            m = re.match(r"^(.*?),\s*([^,]+?),\s*([A-Z]{2})\s+(\d{5})\s*$", n["key"].strip())
            if m:
                parts = dict(street=m.group(1), locality=m.group(2), region=m.group(3), postalCode=m.group(4))
                facet_props.setdefault((nid, "SimpleAddressFacet"), {}).update(parts)
                keyed += [(nid, p, v) for p, v in parts.items()]
            continue
        if kp:
            dest = facet_for(n["type"], kp)
            (facet_props.setdefault((nid, dest), {}) if dest else node_props[nid])[kp] = n["key"]
            keyed.append((nid, kp, n["key"]))
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
    return w, errors, keyed


async def run_case(case_dir: Path, out: Path, cfg: dict, llm) -> dict:
    edc = framework(cfg, out.parent)
    texts = [p["text"] for p in passages(case_dir)]
    shutil.rmtree(out / "edc", ignore_errors=True)
    USAGE.clear()
    CALLS.clear()
    TUPLE_REPLIES.clear()
    try:
        canon = edc.extract_kg(texts, str(out / "edc"))  # writes edc/iter0/result_at_each_stage.json and canon_kg.txt
    finally:
        (out / "llm_calls.jsonl").write_text("".join(json.dumps(c) + "\n" for c in CALLS), encoding="utf-8")
    triples = [t for ts in canon for t in ts if t and len(t) == 3]  # EDC's parser can pass longer lists
    claims, mapping, nodes = claims_of(triples)
    writer, errors, keyed = compile_graph({"edc": claims}, mapping, nodes)
    writer.write(out / "graph.jsonld")
    # What the adapter wrote itself rather than placed: each entity's class, and each key literal taken from an
    # entity string that no EDC triple states. score.py scores c_edc with and without these edges.
    stated = {(mapping.get(f"edc:{a['entity']}"), a["property"], a["value"]) for a in claims["attributes"]
              if isinstance(a["value"], str)}
    (out / "adapter_edges.json").write_text(json.dumps({
        "classes": [{"s": expand(kb_id(nid)), "class": n["type"]} for nid, n in nodes.items()],
        "edges": [{"s": expand(kb_id(nid)), "p": p, "o": v} for nid, p, v in keyed if (nid, p, v) not in stated]}, indent=1))
    return {"status": "ok" if writer.object_count() else "empty", "tokens": dict(USAGE), "inputs": len(texts),
            "edc_triples": len(triples), "tuple_replies_converted": TUPLE_REPLIES["converted"], "nodes": len(nodes),
            "compile_errors": errors[:20]}


if __name__ == "__main__":
    main(ARM, run_case)
