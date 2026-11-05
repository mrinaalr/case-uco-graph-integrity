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


def reconcile_case(graph: Path, docs: Path, out: Path | dict[str, Path], verifier, cfg: dict, *, policy: str,
                   passes: tuple[str, ...], template: str = "plain", passage_unit: str = "block", query: str = "plain",
                   proposals: Path | None = None, add_at: float | None = None) -> dict:
    """One graph through the passes, then decided and written under each policy: `out` is one folder, or
    {policy: folder}; the evidence is gathered once. Returns the first policy's info (every policy's under "policies")."""
    outs = out if isinstance(out, dict) else {policy: out}
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
        info["generated"] = propose_pass(led, src, verifier, margin, add_at if add_at is not None else cfg["selector"]["add_threshold"],
                                        proposals=proposals, case=docs.parent.name, template=template, passage_unit=passage_unit)
    if "readings" in passes:
        from reconcile.readings import readings_pass
        readings_pass(led, src, verifier, margin, claims=list(led))
    meta = {"passes": list(passes), "template": template, "passages": passage_unit, "query": query,
            "contrast_margin": margin, "device": getattr(verifier, "device", None),
            "models": {k: cfg["hook"][k] for k in ("embed_model", "embed_revision", "nli_model", "nli_revision")}}
    gathered = round(time.monotonic() - start, 1)
    results = {}
    for pol, folder in outs.items():
        decide(led, pol, margin)
        this = dict(info)
        if "propose" in passes:
            from reconcile.policy import added
            from reconcile.resolve import drop_unlinked
            this["dropped_entities"] = len(drop_unlinked(led, {c.id for c in added(led, pol)}))
        this.update(emit(led, graph, folder, pol, {**meta, "policy": pol}))
        this["reconcile_s"] = gathered
        results[pol] = {**meta, "policy": pol, **this}
        led.meta["run"] = results[pol]  # beside the ledger, so the caller can read each policy's numbers
        (folder / "ledger" / "ledger.json").write_text(json.dumps(led.meta, indent=1), encoding="utf-8")
    first = results[policy]
    return {**first, "policies": list(results)} if len(results) > 1 else first


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
    ap.add_argument("--policy", default="conservative",
                    help="one of %s; several comma-separated share one pass over the models and write "
                         "<arm>+<suffix> for the first and <arm>+<suffix>-<policy> for the rest" % ", ".join(sorted(POLICIES)))
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
    policies = [p.strip() for p in args.policy.split(",")]
    for p in policies:
        if p not in POLICIES:
            ap.error(f"--policy: {p!r} is not one of {sorted(POLICIES)}")
    common = dict(policy=policies[0], passes=passes, template=args.template, passage_unit=args.passages, query=args.query,
                  proposals=args.proposals, add_at=args.add_at)
    suffixes = {p: args.suffix if i == 0 else f"{args.suffix}-{p}" for i, p in enumerate(policies)}
    if args.graph:
        outs = {p: args.out if i == 0 else args.out.parent / f"{args.out.name}-{p}" for i, p in enumerate(policies)}
        reconcile_case(args.graph, args.docs, outs, verifier, cfg, **common)
        for p, folder in outs.items():
            run = {**json.loads((folder / "ledger" / "ledger.json").read_text())["run"],
                   "final_validation": case_validate(folder / "graph.jsonld")["conforms"]}
            (folder / "run.json").write_text(json.dumps(run, indent=1))
            print(p, json.dumps({k: run[k] for k in ("removed", "added", "merged", "final_validation", "reconcile_s")}))
        return
    root = HARNESS / "results" / args.run_id
    wanted = set(args.cases.split(",")) if args.cases else None
    for case_dir in sorted(p for p in (HARNESS / args.data).iterdir() if p.is_dir() and (not wanted or p.name in wanted)):
        base = root / args.arm / case_dir.name
        outs = {p: root / f"{args.arm}+{s}" / case_dir.name for p, s in suffixes.items()}
        if not (base / "run.json").exists() or (args.resume and all((o / "run.json").exists() for o in outs.values())):
            continue
        meta = json.loads((base / "run.json").read_text())
        infos = {p: {"final_validation": None} for p in outs}
        if meta["status"] not in ("error", "empty") and (base / "graph.jsonld").exists():
            try:
                reconcile_case(base / "graph.jsonld", case_dir / "docs", outs, verifier, cfg, **common)
                for p, folder in outs.items():
                    infos[p] = {**json.loads((folder / "ledger" / "ledger.json").read_text())["run"],
                                "final_validation": case_validate(folder / "graph.jsonld")["conforms"]}
            except Exception as exc:  # an unreadable graph is a recorded outcome, as in the arms
                infos = {p: {"status": "error", "error": f"reconcile: {type(exc).__name__}: {exc}"[:2000],
                             "final_validation": None} for p in outs}
                if os.environ.get("RECONCILE_RAISE"):
                    raise
        for p, folder in outs.items():
            folder.mkdir(parents=True, exist_ok=True)
            info = infos[p]
            run = {**meta, "arm": f"{args.arm}+{suffixes[p]}", "policy": p, **info,
                   "wall_s": round(meta.get("wall_s", 0) + info.get("reconcile_s", 0), 1)}
            (folder / "run.json").write_text(json.dumps(run, indent=1))
            print(f"{run['arm']} {case_dir.name}: {run['status']} removed={info.get('removed')} added={info.get('added')} "
                  f"merged={info.get('merged')} valid={run['final_validation']} {info.get('reconcile_s')}s", flush=True)


if __name__ == "__main__":
    main()
