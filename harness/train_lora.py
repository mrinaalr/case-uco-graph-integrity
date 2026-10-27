"""Placeholder for the trained arms' fine-tuning step (B2, B4).

The trained model is a LoRA of the same base model (Qwen/Qwen3.5-9B) on results/train/b_direct.jsonl,
built by make_training_set.py from data_train (seed 20260202). No benchmark case (data/, seed
20251025) is in the training data. Once the checkpoint is served, put its name in
[models.trained] in config.toml and run:

    python harness/pipeline_monolith.py --run-id RUN --arm b2_trained --model trained
    python harness/pipeline_defended.py --run-id RUN --arm b4_trained_defended --model trained

This script does not train yet. It checks the training file and prints the plan. The Tinker
training API (the `tinker` Python package: LoRA training clients, supervised examples, sampling
from a checkpoint) is not installed in this environment, and its calls are not verified here, so
the training loop is left as an explicit TODO rather than guessed.

    python harness/train_lora.py [--train results/train/b_direct.jsonl]
"""

from __future__ import annotations

import argparse
import json

from graphkit import HARNESS

PLAN = """
Training plan (to implement with the Tinker SDK):
  base model      Qwen/Qwen3.5-9B
  method          LoRA, rank 32, supervised fine-tuning on chat examples
  data            {n} examples from {path}
  held out        the whole benchmark (data/) and the dev set (data_dev/)
  epochs          2, learning rate 1e-4, loss on the assistant turn only
  evaluation      B1 prompt on data_dev every epoch; keep the checkpoint with the best value-scorer recall
  serving         register the checkpoint and set [models.trained].model in harness/config.toml
TODO: implement with tinker.ServiceClient().create_lora_training_client(base_model=...), feed the
examples as supervised datums, save a sampler checkpoint, and record the run id in FROZEN.md.
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="results/train/b_direct.jsonl")
    args = ap.parse_args()
    path = HARNESS / args.train
    if not path.exists():
        raise SystemExit(f"{path} missing: run make_training_set.py first")
    n = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    bad = [i for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()) if line.strip() and
           set(json.loads(line)) != {"messages"}]
    if bad:
        raise SystemExit(f"lines without a messages key: {bad[:5]}")
    print(PLAN.format(n=n, path=path))


if __name__ == "__main__":
    main()
