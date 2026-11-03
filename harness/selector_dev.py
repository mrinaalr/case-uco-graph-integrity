"""Stage the selector's dev check (data_dev only; data/ is test-only) under results/RUN/.

Arms: gold (each dev gold graph), corrupt (hook_dev_check's corrupted copies, with planted wrong-property and
wrong-relation edges), dropped (the gold graph with a share of its object edges removed, seed 0: what a method that
missed them would hand over), and any --real arm copied in (e.g. results/edc-dev/c_edc). Then run hook.py --stage
both and selector.py on each arm, and score.py and meaning.py on the run.

    python harness/selector_dev.py --run-id RUN --from results/lr-dev [--real results/edc-dev/c_edc] [--drop 0.3]
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path

import rdflib
from case_uco.graph import DEFAULT_CONTEXT

from graphkit import HARNESS, graph_triples, load_graph
from hook import remove


def drop(gold: Path, out: Path, share: float, rng: random.Random) -> int:
    g = load_graph(gold)
    _, triples = graph_triples(g)
    nodes = {str(x): x for x in g.all_nodes() if not isinstance(x, rdflib.Literal)}
    objects = [t for t in triples if not t["lit"]]
    gone = rng.sample(objects, round(share * len(objects)))
    for t in gone:
        remove(g, t, nodes)
    out.mkdir(parents=True, exist_ok=True)
    g.serialize(destination=out / "graph.jsonld", format="json-ld", context=DEFAULT_CONTEXT, indent=2)
    (out / "dropped.json").write_text(json.dumps([{k: t[k] for k in ("s", "p", "o")} for t in gone], indent=1))
    return len(gone)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--from", dest="src", required=True, help="a hook_dev_check run with gold and corrupt arms")
    ap.add_argument("--real", action="append", default=[])
    ap.add_argument("--drop", type=float, default=0.3)
    args = ap.parse_args()
    root, src = HARNESS / "results" / args.run_id, HARNESS / args.src
    rng = random.Random(0)
    for arm in ("gold", "corrupt"):
        for case in sorted((src / arm).glob("case_*")):
            dst = root / arm / case.name
            dst.mkdir(parents=True, exist_ok=True)
            for f in ("graph.jsonld", "run.json", "plants.json"):
                if (case / f).exists():
                    shutil.copy(case / f, dst / f)
    for case in sorted((root / "gold").glob("case_*")):
        n = drop(case / "graph.jsonld", root / "dropped" / case.name, args.drop, rng)
        meta = json.loads((case / "run.json").read_text())
        (root / "dropped" / case.name / "run.json").write_text(json.dumps({**meta, "arm": "dropped", "dropped": n}, indent=1))
    for real in args.real:
        real = HARNESS / real
        for case in sorted(real.glob("case_*")):
            dst = root / real.name / case.name
            dst.mkdir(parents=True, exist_ok=True)
            for f in ("graph.jsonld", "run.json", "adapter_edges.json"):
                if (case / f).exists():
                    shutil.copy(case / f, dst / f)
    print(root)


if __name__ == "__main__":
    main()
