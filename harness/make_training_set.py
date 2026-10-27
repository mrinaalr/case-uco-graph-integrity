"""Training pairs for the trained arms (B2, B4) from the training cases, never from the benchmark.

Each training case becomes one chat example: the B1 prompt (same task statement and PDF text the
benchmark arms see) as the user turn, the gold CASE JSON-LD as the assistant turn. Written as
JSONL in the messages format Tinker's supervised fine-tuning takes.

    python harness/make_training_set.py [--data data_train] [--out results/train/b_direct.jsonl]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from graphkit import HARNESS
from llm import SHARED, case_dirs, documents
from pipeline_monolith import PROMPT


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data_train")
    ap.add_argument("--out", default="results/train/b_direct.jsonl")
    args = ap.parse_args()
    if args.data == "data":
        raise SystemExit("refusing to build training data from the benchmark folder")
    out = HARNESS / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out, "w", encoding="utf-8") as fh:
        for case_dir in case_dirs(None, args.data):
            gold = json.loads((case_dir / "gold.jsonld").read_text())
            example = {"messages": [
                {"role": "user", "content": PROMPT.format(shared=SHARED, documents=documents(case_dir))},
                {"role": "assistant", "content": "```json\n" + json.dumps(gold, indent=1) + "\n```"}]}
            fh.write(json.dumps(example) + "\n")
            n += 1
    print(f"{n} examples -> {out}")


if __name__ == "__main__":
    main()
