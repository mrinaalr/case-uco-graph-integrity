"""Check a hook passage mode, or the left and right hooks, on dev gold (data_dev only; data/ is test-only).

Stages two arms under results/RUN/: gold (each dev gold graph, every edge true) and corrupt (the same graph with
false edges made from its own values: each message's sender and first recipient swapped; sentTime, startTime and
every Relationship target rotated one place among the edges of the same property or kind). Into corrupt it also
plants edges that say a true value or link under the wrong property or relation (PLANTS), each listed in
plants.json: wrong_property (a message's sentTime as receivedTime, an event's startTime as endTime, an account's
identifier as its name, a street as the locality; one per case each) and wrong_relation (the swapped sender and
recipient; a pair of a gold relation under another kind or reversed, and an account's owner as its issuer; the first
relation of each kind). Runs hook.py on both in each --passages mode and reports, per mode: true edges kept by
property (gold), false edges removed (corrupt), kept true edges citing their gold sentence, and rendered sentences
that repeat their subject's label as the value. An edge is true when the strict scorer matches it to a dev gold
triple.

--stages runs hook.py --stage left,right,both instead and reports each stage: true edges kept, planted edges
removed (and those the left hook keeps that the right hook removes), other false edges removed, citation
accuracy, each right check's coverage, and the left+right decision at each --margins value, recomputed from the
rows. --real copies an arm's dev graphs (e.g. results/edc-dev/c_edc) in as a third arm.

    python harness/hook_dev_check.py --run-id RUN [--cases case_01,...] [--modes sentence,block]
    python harness/hook_dev_check.py --run-id RUN --stages [--real results/edc-dev/c_edc] [--margins 0,1,2,3]
                                     [--resume] [--report-only]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import rdflib

from case_uco.graph import DEFAULT_CONTEXT
from graphkit import HARNESS, REPO, SCHEMA, expand, graph_triples, load_graph
from hook import CHECKS, contrast_result, label, mention
from score import norm_text, score_case

FROM, TO = rdflib.URIRef(expand("uco-observable:from")), rdflib.URIRef(expand("uco-observable:to"))
ROTATED = [rdflib.URIRef(expand(p)) for p in ("uco-observable:sentTime", "uco-core:startTime")]
KIND, TARGET = rdflib.URIRef(expand("uco-core:kindOfRelationship")), rdflib.URIRef(expand("uco-core:target"))
SOURCE, HAS_FACET = rdflib.URIRef(expand("uco-core:source")), rdflib.URIRef(expand("uco-core:hasFacet"))
# Planted wrong_property: (class holding the property, gold property, wrong property, the wrong property's holder).
PLANTS = [("EmailMessageFacet", "sentTime", "receivedTime", "facet"), ("Event", "startTime", "endTime", "node"),
          ("AccountFacet", "accountIdentifier", "name", "owner"), ("SimpleAddressFacet", "street", "locality", "facet")]
# Planted wrong_relation: gold kind -> (planted kind, reversed).
KIND_PLANTS = {"Reports_To": ("Reports_To", True), "Employed_By": ("Employed_By", True),
               "Located_At": ("Located_At", True), "Initiated": ("Authorized", False), "Authorized": ("Initiated", False),
               "Participated_In": ("Initiated", False), "Holds_Account": ("Owns_Account", False)}


def rotate(g: rdflib.Graph, pred: rdflib.URIRef, holders: list | None = None) -> None:
    """Move each object one place along the holders of pred (sorted), when they hold at least two distinct values."""
    pairs = sorted(((s, o) for s, o in g.subject_objects(pred) if holders is None or s in holders), key=lambda x: str(x[0]))
    if len({o for _, o in pairs}) < 2:
        return
    for (s, o), (_, new) in zip(pairs, pairs[1:] + pairs[:1]):
        g.remove((s, pred, o))
        g.add((s, pred, new))


def corrupt(gold: Path, out: Path) -> None:
    g = load_graph(gold)
    true = {(t["s"], t["p"], t["o"]) for t in graph_triples(g)[1]}
    owner = {f: s for s, f in g.subject_objects(HAS_FACET)}
    plants = []

    def plant(s, p, o, kind, how) -> None:
        if (str(s), p, str(o)) not in true:
            plants.append({"s": str(s), "p": p, "o": str(o), "plant": kind, "how": how})
    for facet in sorted(set(g.subjects(FROM, None)), key=str):
        sender, recipients = next(g.objects(facet, FROM)), sorted(g.objects(facet, TO), key=str)
        if recipients:
            g.remove((facet, FROM, sender))
            g.remove((facet, TO, recipients[0]))
            g.add((facet, FROM, recipients[0]))
            g.add((facet, TO, sender))
            plant(owner[facet], "from", recipients[0], "wrong_relation", "sender and recipient swapped")
            plant(owner[facet], "to", sender, "wrong_relation", "sender and recipient swapped")
    for pred in ROTATED:
        rotate(g, pred)
    rels = {(str(k), r): (next(g.objects(r, SOURCE)), next(g.objects(r, TARGET))) for k, r in
            ((k, r) for r, k in g.subject_objects(KIND))}  # pairs before rotation
    for kind in {str(k) for k in g.objects(None, KIND)}:
        rotate(g, TARGET, [r for r in g.subjects(KIND, rdflib.Literal(kind))])
    gold_g = load_graph(gold)  # the true values, before rotation
    for cls, prop, wrong, where in PLANTS:
        pred = rdflib.URIRef(expand(SCHEMA[cls]["props"][prop]["key"]))
        holders = sorted(((h, v) for h, v in gold_g.subject_objects(pred)
                          if (rdflib.RDF.type, rdflib.URIRef(expand(SCHEMA[cls]["type"]))) in gold_g.predicate_objects(h)),
                         key=lambda x: str(x[0]))
        if holders:
            h, v = holders[0]
            node = h if where in ("facet", "node") else owner[h]
            g.add((node, rdflib.URIRef(expand(SCHEMA["UcoObject" if wrong == "name" else cls]["props"][wrong]["key"])), v))
            plant(owner.get(h, h), wrong, v, "wrong_property", f"{prop} as {wrong}")
    issuer = rdflib.URIRef(expand("uco-observable:accountIssuer"))
    for gold_kind, (kind, reverse) in KIND_PLANTS.items():
        first = sorted((r for (k, r) in rels if k == gold_kind), key=str)
        if not first:
            continue
        src, tgt = rels[(gold_kind, first[0])]
        src, tgt = (tgt, src) if reverse else (src, tgt)
        if (str(src), kind, str(tgt)) in true:
            continue
        r = rdflib.URIRef(f"{first[0]}-plant")
        for p, o in ((rdflib.RDF.type, rdflib.URIRef(expand("uco-core:Relationship"))), (SOURCE, src), (TARGET, tgt),
                     (KIND, rdflib.Literal(kind))):
            g.add((r, p, o))
        plant(src, kind, tgt, "wrong_relation", f"{gold_kind} {'reversed' if reverse else 'as ' + kind}")
    owns = sorted((r for (k, r) in rels if k == "Owns_Account"), key=str)
    for r in owns[:1]:  # the owner as the account's issuer
        org, acct = rels[("Owns_Account", r)]
        facet = next((f for f in g.objects(acct, HAS_FACET) if (f, issuer, None) in g), None)
        if facet is not None and (str(acct), "accountIssuer", str(org)) not in true:
            g.add((facet, issuer, org))
            plant(acct, "accountIssuer", org, "wrong_relation", "owner as issuer")
    g.serialize(destination=out, format="json-ld", context=DEFAULT_CONTEXT, indent=2)
    (out.parent / "plants.json").write_text(json.dumps(plants, indent=1))


def stage(root: Path, cases: list[str]) -> None:
    shutil.rmtree(root, ignore_errors=True)
    for case in cases:
        for arm in ("gold", "corrupt"):
            d = root / arm / case
            d.mkdir(parents=True)
            src = HARNESS / "data_dev" / case / "gold.jsonld"
            shutil.copy(src, d / "graph.jsonld") if arm == "gold" else corrupt(src, d / "graph.jsonld")
            (d / "run.json").write_text(json.dumps({"case_id": case, "status": "ok", "tokens": {"prompt": 0, "completion": 0}}))


def report(root: Path, cases: list[str], mode: str) -> None:
    suffix = "+hook_block" if mode == "block" else "+hook"
    kept, cite, false, taut = defaultdict(Counter), Counter(), Counter(), 0
    for case in cases:
        case_dir = HARNESS / "data_dev" / case
        spans = json.loads((case_dir / "spans.json").read_text())
        span_of = {t["tid"]: spans[t["span_id"]] for t in json.loads((case_dir / "gold.json").read_text())["triples"]}
        for arm in ("gold", "corrupt"):
            graph = root / arm / case / "graph.jsonld"
            tid_of = {(s, p, o): tid for s, p, o, tid in score_case(case_dir, graph)["matched"]}
            ents, triples = graph_triples(load_graph(graph))
            taut += sum(1 for t in triples if t["lit"] and (lab := label(t["s"], ents)) and t["o"] in lab[1]
                        and mention(t["s"], ents, t["o"]).startswith(lab[1]))
            for r in map(json.loads, (root / f"{arm}{suffix}" / case / "hook.jsonl").read_text().splitlines()):
                tid = tid_of.get((r["s"], r["p"], r["o"]))
                if arm == "corrupt" and tid is None:
                    false["edges"] += 1
                    false["removed"] += not r["kept"]
                    false[f"removed {r['p']}"] += not r["kept"]
                    false[f"edges {r['p']}"] += 1
                elif arm == "gold" and tid is not None:
                    kept[r["p"]]["n"] += 1
                    kept[r["p"]]["kept"] += r["kept"]
                    if r["kept"]:
                        span, c = span_of[tid], r["cited"]
                        cite["kept"] += 1
                        cite["correct"] += c["doc"] == span["doc_id"] and norm_text(span["text"]) in norm_text(c["text"])
    n, k = sum(c["n"] for c in kept.values()), sum(c["kept"] for c in kept.values())
    print(f"\n--passages {mode}: {len(cases)} dev cases")
    print(f"  true edges kept (gold): {k}/{n} = {k / n:.2%}")
    for p, c in sorted(kept.items(), key=lambda x: x[1]["kept"] / x[1]["n"]):
        if c["kept"] < c["n"]:
            print(f"    {p}: {c['kept']}/{c['n']} = {c['kept'] / c['n']:.0%}")
    print(f"  false edges removed (corrupt): {false['removed']}/{false['edges']} = {false['removed'] / false['edges']:.1%}")
    for p in sorted({k.split(' ', 1)[1] for k in false if k.startswith("edges ")}):
        print(f"    {p}: {false['removed ' + p]}/{false['edges ' + p]}")
    print(f"  kept true edges citing their gold sentence: {cite['correct']}/{cite['kept']} = {cite['correct'] / cite['kept']:.1%}")
    print(f"  rendered sentences whose subject label holds the value: {taut}")


def report_stages(root: Path, cases: list[str], arms: list[str], margins: list[float]) -> None:
    """Per arm and stage: true edges kept, planted and other false edges removed, citations, check coverage."""
    for arm in arms:
        print(f"\n{arm}: {len(cases)} dev cases")
        for stage in ("left", "right", "lr"):
            c, cov = Counter(), {k: Counter() for k in CHECKS}
            sweep = {m: Counter() for m in margins} if stage == "lr" else {}
            for case in cases:
                case_dir, graph = HARNESS / "data_dev" / case, root / arm / case / "graph.jsonld"
                hooked = root / f"{arm}+{stage}" / case / "hook.jsonl"
                if not hooked.exists():
                    continue
                spans = json.loads((case_dir / "spans.json").read_text())
                span_of = {t["tid"]: spans[t["span_id"]] for t in json.loads((case_dir / "gold.json").read_text())["triples"]}
                tid_of = {(s, p, o): tid for s, p, o, tid in score_case(case_dir, graph)["matched"]}
                cls_of = {(u["s"], u["p"], u["o"]): u["class"] for u in score_case(case_dir, graph, scorer="value")["unsupported"]}
                plants = root / arm / case / "plants.json"
                plant_of = {(x["s"], x["p"], x["o"]): x["plant"] for x in json.loads(plants.read_text())} if plants.exists() else {}
                for r in map(json.loads, hooked.read_text().splitlines()):
                    key = (r["s"], r["p"], r["o"])
                    kind = "true" if key in tid_of else plant_of.get(key) or (f"other {cls_of[key]}" if key in cls_of else None)
                    if kind is None:  # a repeat of an edge already counted
                        continue
                    c[kind] += 1
                    c[f"{kind} kept"] += r["kept"]
                    c[f"{kind} left kept, right removed"] += r["left"]["kept"] and r["removed_by"] == "right"
                    for m, sc in sweep.items():
                        sc[kind] += 1
                        sc[f"{kind} kept"] += r["left"]["kept"] and all(v["result"] != "fail" for k, v in (r["right"] or {}).items()
                                                                         if k != "contrast") and \
                            (not r["right"] or contrast_result(r, m)[0]["result"] != "fail")
                    if kind == "true" and r["kept"] and r["cited"]:
                        span = span_of[tid_of[key]]
                        c["cited"] += 1
                        c["cited correct"] += r["cited"]["doc"] == span["doc_id"] and norm_text(span["text"]) in norm_text(r["cited"]["text"])
                    for k, v in (r["right"] or {}).items():
                        cov[k][v["result"]] += 1
            kinds = ["true", "wrong_property", "wrong_relation"] + sorted(k for k in c if k.startswith("other ") and " " not in k[6:])
            print(f"  +{stage}: " + "; ".join(
                f"{k} kept {c[k + ' kept']}/{c[k]}" + (f" (left kept, right removed {c[k + ' left kept, right removed']})"
                                                     if stage == "lr" and c[k + ' left kept, right removed'] else "")
                for k in kinds if c[k]) + (f"; cited correct {c['cited correct']}/{c['cited']}" if c["cited"] else ""))
            if stage != "left":
                print("    coverage (pass/fail/skip): " + ", ".join(
                    f"{k} {v['pass']}/{v['fail']}/{v['skip']}" for k, v in cov.items()))
            for m, sc in sweep.items():
                print(f"    margin {m}: " + "; ".join(f"{k} kept {sc[k + ' kept']}/{sc[k]}" for k in kinds if sc[k]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--cases", default=",".join(f"case_{i:02d}" for i in range(1, 9)))
    ap.add_argument("--modes", default="sentence,block")
    ap.add_argument("--stages", action="store_true", help="the left and right hooks instead of the passage modes")
    ap.add_argument("--real", type=Path, help="--stages: an arm's dev graphs to check too, e.g. results/edc-dev/c_edc")
    ap.add_argument("--margins", default="0,1,2,3,4", help="--stages: contrast margins in log-odds")
    ap.add_argument("--resume", action="store_true", help="--stages: keep the staged graphs and finished cases")
    ap.add_argument("--report-only", action="store_true", help="--stages: report from the rows already written")
    args = ap.parse_args()
    cases, root = args.cases.split(","), HARNESS / "results" / args.run_id
    if args.stages:
        arms = ["gold", "corrupt"] + ([args.real.name] if args.real else [])
        if not args.report_only:
            if not args.resume:
                stage(root, cases)
            for case in cases if args.real else []:
                src, dst = HARNESS / args.real / case, root / args.real.name / case
                if (src / "run.json").exists() and not (dst / "run.json").exists():
                    dst.mkdir(parents=True, exist_ok=True)
                    for f in ("graph.jsonld", "run.json", "adapter_edges.json"):
                        if (src / f).exists():
                            shutil.copy(src / f, dst / f)
            for arm in arms:
                subprocess.run([str(REPO / ".venv" / "bin" / "python"), str(HARNESS / "hook.py"), "--run-id", args.run_id,
                                "--arm", arm, "--data", "data_dev", "--cases", args.cases, "--stage", "left,right,both",
                                *(["--resume"] if args.resume else [])], check=True)
        return report_stages(root, cases, arms, [float(m) for m in args.margins.split(",")])
    stage(root, cases)
    for mode in args.modes.split(","):
        for arm in ("gold", "corrupt"):
            subprocess.run([str(REPO / ".venv" / "bin" / "python"), str(HARNESS / "hook.py"), "--run-id", args.run_id,
                            "--arm", arm, "--data", "data_dev", "--cases", args.cases, "--passages", mode],
                           check=True, capture_output=True)
        report(root, cases, mode)


if __name__ == "__main__":
    main()
