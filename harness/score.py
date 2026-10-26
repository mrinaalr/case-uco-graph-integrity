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

from graphkit import HARNESS, graph_triples, iso_time

SCORERS = ("strict", "value")
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
        if s and (t["lit"] or o) and (s, p, o) in gold_keys:
            supported.add((s, p, o))
            continue
        if scorer == "value" and s and p in CONTAINS_PROPS:
            hit = next((k for k in gold_keys if k[:2] == (s, p) and value_matches(p, k[2], t["o"])), None)
            if hit:
                supported.add(hit)
                continue
        if t["s"] in duplicates or (not t["lit"] and t["o"] in duplicates):
            cls = "duplicate_entity"
        else:
            cls = classify(gold, s, p, o, t, merged, linked, scorer)
        stage, call, cited = lookup(t["origin"])
        unsupported.append({"s": t["s"], "p": t["p"], "o": t["o"], "aligned_s": s, "aligned_o": None if t["lit"] else o,
                            "class": cls, "stage": stage, "call": call, "cited_spans": cited})
    n_emitted = len(seen)
    aligned_classes = [emitted[i]["class"] == gold["ents"][g]["class"] for i, g in primary.items()]
    return {
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
        "tokens_prompt": sum(r["tokens"]["prompt"] for r in rows),
        "tokens_completion": sum(r["tokens"]["completion"] for r in rows),
        "wall_s_total": round(sum(r.get("wall_s", 0) for r in rows), 1),
        "wall_s_mean": mean(r.get("wall_s") for r in rows),
        "failed_cases": " ".join(r["case_id"] for r in failed),
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
    stages = sorted({k for c in stage_counts.values() for k in c})
    lines += ["\n## Unsupported triples by first stage\n"]
    lines += table(["arm", "scorer"] + stages, [[arm, sc] + [c.get(k, 0) for k in stages] for (arm, sc), c in stage_counts.items()])
    lines += ["\n## Failures (zero recall)\n"] + [f"- {s['arm']}: {s['failed_cases'] or 'none'}"
                                                   for s in summaries if s["scorer"] == "strict"]
    return "\n".join(lines) + "\n"


def variants(arm: str, run_dir: Path) -> list[tuple[str, str, str, str | None]]:
    """(label, graph file, score file, prov file) to score for one case run."""
    if arm != "a2_tools":
        return [(arm, "graph.jsonld", "score.json", None)]
    early = "graph_first_validate.jsonld" if (run_dir / "graph_first_validate.jsonld").exists() else "graph.jsonld"
    early_prov = "prov_first_validate.json" if early != "graph.jsonld" else "prov.json"  # never validated: same graph
    return [(f"{arm}@first_validate", early, "score_first_validate.json", early_prov),
            (arm, "graph.jsonld", "score.json", "prov.json")]


def score_run(run_id: str) -> None:
    run_root = HARNESS / "results" / run_id
    groups: dict[tuple[str, str], list[dict]] = {}
    for arm_dir in sorted(p for p in run_root.iterdir() if p.is_dir()):
        for run_dir in sorted(p for p in arm_dir.iterdir() if p.is_dir()):
            meta = json.loads((run_dir / "run.json").read_text())
            data_dir = HARNESS / "data" / run_dir.name
            for label, graph_name, score_name, prov in variants(arm_dir.name, run_dir):
                for scorer in SCORERS:
                    row = dict(meta, arm=label, scorer=scorer)
                    if label.endswith("@first_validate") and meta.get("server_validations"):
                        row["final_validation"] = meta["server_validations"][0]
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
                   **{c: r.get("unsupported_by_class", {}).get(c, 0) for c in CLASSES}}
                for rows in groups.values() for r in rows]
    for name, rows in (("summary.csv", summaries), ("per_case.csv", per_case)):
        with open(run_root / name, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    (run_root / "summary.md").write_text(markdown(summaries, stage_counts))
    print((run_root / "summary.md").read_text())


def self_test() -> None:
    for scorer in SCORERS:
        for case_dir in sorted(p for p in (HARNESS / "data").iterdir() if p.is_dir()):
            r = score_case(case_dir, case_dir / "gold.jsonld", scorer=scorer)
            assert r["precision"] == 1 and r["recall"] == 1, (scorer, case_dir.name, r["unsupported"][:3], r["missed"][:3])
        print(f"self-test ok ({scorer}): every gold graph scores P=R=1 against itself")


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
