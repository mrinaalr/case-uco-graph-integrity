"""Reconcile a graph against its documents.

    python harness/reconcile/run.py --graph G.jsonld --docs DIR --out DIR [--policy conservative] [--passes verify,readings,propose]
    python harness/reconcile/run.py --run-id RUN --arm b_control [--data data_dev] [--suffix rec] [--cases ...] [--resume]

The second form reads results/RUN/<arm>/<case>/graph.jsonld for each case of the data folder and writes
results/RUN/<arm>+<suffix>/<case>/, so score.py and meaning.py score it like any arm. `--passes` picks the passes:
verify (backward verification of the stated claims), propose (forward recovery: the proposals, with the same
evidence) and readings (the ontology's checks and contrast on every claim with support, stated and proposed
together, so a wrong edge and its right reading are decided from the same passages). `--policy hook-v1` with
`--template full --passages sentence --query rendered` is the published hook decided from the ledger, for parity."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/, for the bare-name imports

from graphkit import HARNESS, case_validate  # noqa: E402
from reconcile import ontology  # noqa: E402  (validates the profile at import)
from reconcile.emit import emit  # noqa: E402
from reconcile.ingest import ingest  # noqa: E402
from reconcile.ledger import Ledger  # noqa: E402
from reconcile.policy import POLICIES, decide  # noqa: E402
from reconcile.source import Source  # noqa: E402
from reconcile.verify import verify  # noqa: E402

PASSES = ("verify", "propose", "readings")
CONFIG = HARNESS / "config.toml"


def load_cfg() -> dict:
    with open(CONFIG, "rb") as fh:
        return tomllib.load(fh)


def reconcile_case(graph: Path, docs: Path, out: Path, verifier, cfg: dict, *, policy: str, passes: tuple[str, ...],
                   template: str = "plain", passage_unit: str = "block", query: str = "plain", proposals: Path | None = None,
                   add_at: float | None = None) -> dict:
    start = time.monotonic()
    src = Source(docs, cfg.get("data", {}).get("source", "pdf"))
    led, _ = ingest(graph)
    margin = cfg["hook"]["contrast_margin"]
    legacy = policy == "hook-v1"
    info = {}
    if "verify" in passes:
        verify(led, src, verifier, template=template, passage_unit=passage_unit, query=query, linked=not legacy)
    if "propose" in passes:  # proposals are made before the checks, so stated and proposed claims are checked together
        from reconcile.propose import propose_pass
        info["proposed"] = propose_pass(led, src, verifier, margin, add_at if add_at is not None else cfg["selector"]["add_threshold"],
                                        proposals=proposals, case=docs.parent.name, template=template, passage_unit=passage_unit)
    if "readings" in passes:
        from reconcile.readings import readings_pass
        readings_pass(led, src, verifier, margin, claims=list(led))
    decide(led, policy, margin)
    if "propose" in passes:
        from reconcile.policy import added
        from reconcile.resolve import drop_unlinked
        info["dropped_entities"] = len(drop_unlinked(led, {c.id for c in added(led, policy)}))
    meta = {"passes": list(passes), "template": template, "passages": passage_unit, "query": query,
            "contrast_margin": margin, "device": getattr(verifier, "device", None),
            "models": {k: cfg["hook"][k] for k in ("embed_model", "embed_revision", "nli_model", "nli_revision")}}
    info.update(emit(led, graph, out, policy, meta))
    info["reconcile_s"] = round(time.monotonic() - start, 1)
    return {**meta, **info}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", type=Path)
    ap.add_argument("--docs", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--run-id")
    ap.add_argument("--arm")
    ap.add_argument("--data", default="data")
    ap.add_argument("--suffix", default="rec")
    ap.add_argument("--cases")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--policy", default="conservative", choices=sorted(POLICIES))
    ap.add_argument("--passes", default="verify,readings,propose")
    ap.add_argument("--template", default="plain", choices=("full", "labels", "plain"))
    ap.add_argument("--passages", default="block", choices=("sentence", "block"))
    ap.add_argument("--query", default="plain", choices=("rendered", "plain"))
    ap.add_argument("--proposals", type=Path, help="folder of cached LLM proposals, <case>.json (propose pass)")
    ap.add_argument("--add-at", type=float)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--stub", action="store_true", help="the test suite's stub verifier, no models (smoke runs only)")
    args = ap.parse_args()
    passes = tuple(p for p in PASSES if p in {x.strip() for x in args.passes.split(",")})
    cfg = load_cfg()
    if args.stub:
        sys.path.insert(0, str(HARNESS / "tests"))
        from conftest import StubVerifier
        verifier = StubVerifier(cfg["hook"]["top_k"])
    else:
        from hook import Verifier
        verifier = Verifier(cfg["hook"], args.batch)
    common = dict(policy=args.policy, passes=passes, template=args.template, passage_unit=args.passages, query=args.query,
                  proposals=args.proposals, add_at=args.add_at)
    if args.graph:
        info = reconcile_case(args.graph, args.docs, args.out, verifier, cfg, **common)
        info["final_validation"] = case_validate(args.out / "graph.jsonld")["conforms"]
        (args.out / "run.json").write_text(json.dumps(info, indent=1))
        print(json.dumps({k: info[k] for k in ("removed", "added", "merged", "final_validation", "reconcile_s")}))
        return
    root = HARNESS / "results" / args.run_id
    wanted = set(args.cases.split(",")) if args.cases else None
    for case_dir in sorted(p for p in (HARNESS / args.data).iterdir() if p.is_dir() and (not wanted or p.name in wanted)):
        base = root / args.arm / case_dir.name
        out = root / f"{args.arm}+{args.suffix}" / case_dir.name
        if not (base / "run.json").exists() or (args.resume and (out / "run.json").exists()):
            continue
        meta = json.loads((base / "run.json").read_text())
        info = {"final_validation": None}
        if meta["status"] not in ("error", "empty") and (base / "graph.jsonld").exists():
            try:
                info = reconcile_case(base / "graph.jsonld", case_dir / "docs", out, verifier, cfg, **common)
                info["final_validation"] = case_validate(out / "graph.jsonld")["conforms"]
            except Exception as exc:  # an unreadable graph is a recorded outcome, as in the arms
                info = {"status": "error", "error": f"reconcile: {type(exc).__name__}: {exc}"[:2000], "final_validation": None}
                if os.environ.get("RECONCILE_RAISE"):
                    raise
        out.mkdir(parents=True, exist_ok=True)
        run = {**meta, "arm": f"{args.arm}+{args.suffix}", **info, "wall_s": round(meta.get("wall_s", 0) + info.get("reconcile_s", 0), 1)}
        (out / "run.json").write_text(json.dumps(run, indent=1))
        print(f"{run['arm']} {case_dir.name}: {run['status']} removed={info.get('removed')} added={info.get('added')} "
              f"merged={info.get('merged')} valid={run['final_validation']} {info.get('reconcile_s')}s", flush=True)


if __name__ == "__main__":
    main()
