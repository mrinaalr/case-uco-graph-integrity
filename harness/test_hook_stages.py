"""The left and right hooks (hook.py --stage). On dev gold and hook_dev_check's corrupted dev graphs:

1. An edge the left hook removes never reaches an output the left hook feeds: in +left and +lr it is not kept, is
   absent from the hooked graph, and in +lr the right hook never ran on it.
2. The right hook removes planted wrong-property and wrong-relation edges the left hook keeps (+lr).
3. score.py --self-test passes on a fresh clone: the tracked files only, so no PDF text caches, with mcp unimportable.

    python harness/test_hook_stages.py [--cases case_01,case_02,case_03] [--no-clone]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from graphkit import HARNESS, REPO, graph_triples
from hook_dev_check import stage

RUN_ID = "test-hook-stages"
PYTHON = str(REPO / ".venv" / "bin" / "python")


def fresh_clone() -> str | None:
    """Copy the files a clone would have (tracked and new, not ignored; no submodules) and run the self-test there."""
    tmp = Path(tempfile.mkdtemp())
    try:
        files = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=REPO, capture_output=True,
                               text=True, check=True).stdout.splitlines()
        for f in files:
            if (REPO / f).is_file():
                (tmp / f).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPO / f, tmp / f)
        if list((tmp / "harness").rglob("*.pdf.txt")):
            return "the copy has PDF text caches"
        block_mcp = "import runpy, sys; sys.modules['mcp'] = None; sys.argv = ['score.py', '--self-test']; " \
                    "runpy.run_path('score.py', run_name='__main__')"
        proc = subprocess.run([PYTHON, "-c", block_mcp], cwd=tmp / "harness", capture_output=True, text=True)
        if proc.returncode:
            return f"self-test failed:\n{proc.stdout[-1500:]}{proc.stderr[-1500:]}"
        print(proc.stdout.strip())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="case_01,case_02,case_03")
    ap.add_argument("--no-clone", action="store_true", help="skip the fresh-clone self-test")
    args = ap.parse_args()
    cases, root = args.cases.split(","), HARNESS / "results" / RUN_ID
    stage(root, cases)
    for arm in ("gold", "corrupt"):
        subprocess.run([PYTHON, str(HARNESS / "hook.py"), "--run-id", RUN_ID, "--arm", arm, "--data", "data_dev",
                        "--cases", args.cases, "--stage", "left,right,both"], check=True, capture_output=True)
    failures, removed, planted = [], 0, Counter()
    for arm in ("gold", "corrupt"):
        for case in cases:
            plants = {(x["s"], x["p"], x["o"]): x["plant"]
                      for x in json.loads((root / arm / case / "plants.json").read_text())} if arm == "corrupt" else {}
            for st in ("left", "lr"):
                out = root / f"{arm}+{st}" / case
                kept = {(t["s"], t["p"], t["o"]) for t in graph_triples(out / "graph.jsonld")[1]}
                for r in map(json.loads, (out / "hook.jsonl").read_text().splitlines()):
                    key = (r["s"], r["p"], r["o"])
                    if not r["left"]["kept"]:
                        removed += 1
                        if r["kept"] or r["removed_by"] != "left" or key in kept or (st == "lr" and r["right"]):
                            failures.append(f"{arm}+{st} {case}: left-removed edge reached the output: {r['sentence']}")
                    if st == "lr" and key in plants and r["left"]["kept"]:
                        planted[f"{plants[key]} left kept"] += 1
                        planted[f"{plants[key]} right removed"] += r["removed_by"] == "right"
    for kind in ("wrong_property", "wrong_relation"):
        if not planted[f"{kind} right removed"]:
            failures.append(f"the right hook removed none of the {planted[f'{kind} left kept']} planted {kind} edges "
                            f"the left hook kept")
    if not args.no_clone and (err := fresh_clone()):
        failures.append(err)
    shutil.rmtree(root, ignore_errors=True)
    if failures:
        sys.exit("FAIL\n" + "\n".join(failures))
    print(f"ok: {removed} left-removed edges reach no +left or +lr output; the right hook removed "
          f"{planted['wrong_property right removed']}/{planted['wrong_property left kept']} wrong-property and "
          f"{planted['wrong_relation right removed']}/{planted['wrong_relation left kept']} wrong-relation plants the "
          f"left hook kept" + ("" if args.no_clone else "; the fresh-clone self-test passes"))


if __name__ == "__main__":
    main()
