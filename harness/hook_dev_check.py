"""Check a hook passage mode on dev gold (data_dev only; data/ is test-only).

Stages two arms under results/RUN/: gold (each dev gold graph, every edge true) and corrupt (the same graph with
false edges made from its own values: each message's sender and first recipient swapped; sentTime, startTime and
every Relationship target rotated one place among the edges of the same property or kind). Runs hook.py on both
in each --passages mode and reports, per mode: true edges kept by property (gold), false edges removed (corrupt),
kept true edges citing their gold sentence, and rendered sentences that repeat their subject's label as the value.
An edge is true when the strict scorer matches it to a dev gold triple.

    python harness/hook_dev_check.py --run-id RUN [--cases case_01,...] [--modes sentence,block]
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
from graphkit import HARNESS, REPO, expand, graph_triples, load_graph
from hook import label, mention
from score import norm_text, score_case

FROM, TO = rdflib.URIRef(expand("uco-observable:from")), rdflib.URIRef(expand("uco-observable:to"))
ROTATED = [rdflib.URIRef(expand(p)) for p in ("uco-observable:sentTime", "uco-core:startTime")]
KIND, TARGET = rdflib.URIRef(expand("uco-core:kindOfRelationship")), rdflib.URIRef(expand("uco-core:target"))


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
    for facet in set(g.subjects(FROM, None)):
        sender, recipients = next(g.objects(facet, FROM)), sorted(g.objects(facet, TO), key=str)
        if recipients:
            g.remove((facet, FROM, sender))
            g.remove((facet, TO, recipients[0]))
            g.add((facet, FROM, recipients[0]))
            g.add((facet, TO, sender))
    for pred in ROTATED:
        rotate(g, pred)
    for kind in {str(k) for k in g.objects(None, KIND)}:
        rotate(g, TARGET, [r for r in g.subjects(KIND, rdflib.Literal(kind))])
    g.serialize(destination=out, format="json-ld", context=DEFAULT_CONTEXT, indent=2)


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--cases", default=",".join(f"case_{i:02d}" for i in range(1, 9)))
    ap.add_argument("--modes", default="sentence,block")
    args = ap.parse_args()
    cases, root = args.cases.split(","), HARNESS / "results" / args.run_id
    stage(root, cases)
    for mode in args.modes.split(","):
        for arm in ("gold", "corrupt"):
            subprocess.run([str(REPO / ".venv" / "bin" / "python"), str(HARNESS / "hook.py"), "--run-id", args.run_id,
                            "--arm", arm, "--data", "data_dev", "--cases", args.cases, "--passages", mode],
                           check=True, capture_output=True)
        report(root, cases, mode)


if __name__ == "__main__":
    main()
