"""The hook keeps true header facts: an email's sentTime and recipient, stated on a Date: or To: line that does not
name the message. Runs hook.py end to end on dev gold graphs (every edge true) and checks that each edge below is
kept and cites a passage that holds its gold line.

    python harness/test_hook.py [--passages MODE]   # MODE is passed to hook.py; omitted, hook.py's default
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys

from graphkit import HARNESS, REPO
from score import norm_text, score_case

RUN_ID = "test-hook"
EDGES = {"case_01": ["t60", "t58"], "case_02": ["t57", "t54"]}  # sentTime (Date: line), to (To: line)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--passages")
    args = ap.parse_args()
    root = HARNESS / "results" / RUN_ID
    shutil.rmtree(root, ignore_errors=True)
    for case in EDGES:
        d = root / "gold" / case
        d.mkdir(parents=True)
        shutil.copy(HARNESS / "data_dev" / case / "gold.jsonld", d / "graph.jsonld")
        (d / "run.json").write_text(json.dumps({"case_id": case, "status": "ok", "tokens": {"prompt": 0, "completion": 0}}))
    cmd = [str(REPO / ".venv" / "bin" / "python"), str(HARNESS / "hook.py"), "--run-id", RUN_ID, "--arm", "gold",
           "--data", "data_dev", "--cases", ",".join(EDGES)] + (["--passages", args.passages] if args.passages else [])
    subprocess.run(cmd, check=True, capture_output=True)
    hooked = root / ("gold+hook_block" if args.passages == "block" else "gold+hook")
    failures = []
    for case, tids in EDGES.items():
        case_dir = HARNESS / "data_dev" / case
        edge_of = {tid: (s, p, o) for s, p, o, tid in score_case(case_dir, case_dir / "gold.jsonld")["matched"]}
        gold = {t["tid"]: t for t in json.loads((case_dir / "gold.json").read_text())["triples"]}
        spans = json.loads((case_dir / "spans.json").read_text())
        rows = {(r["s"], r["p"], r["o"]): r for r in map(json.loads, (hooked / case / "hook.jsonl").read_text().splitlines())}
        for tid in tids:
            r, span = rows[edge_of[tid]], spans[gold[tid]["span_id"]]
            if not r["kept"]:
                failures.append(f"{case} {tid} {r['p']}: removed ({r['verdict']}); gold line {span['text']!r}")
            elif r["cited"]["doc"] != span["doc_id"] or norm_text(span["text"]) not in norm_text(r["cited"]["text"]):
                failures.append(f"{case} {tid} {r['p']}: kept, but cites {r['cited']['text']!r}")
    if failures:
        sys.exit("FAIL\n" + "\n".join(failures))
    print(f"ok: {sum(map(len, EDGES.values()))} header edges kept, each citing its gold line")


if __name__ == "__main__":
    main()
