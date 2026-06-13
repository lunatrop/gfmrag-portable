"""Split the remaining ladder rungs (shard-4, shard-5) into balanced
production sub-shards, each <= MAX_DOCS so it finishes inside the 1h GPU task
cap. Stages the au-register profile into each. Stdlib only.

    python scripts/prepare_campaign_shards.py [--max-docs 700] [--out corpus-campaign]
"""
import argparse
import glob
import json
import math
import os
import shutil
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--rungs", nargs="+", default=["shard-4", "shard-5"])
ap.add_argument("--src", default="corpus-shards")
ap.add_argument("--out", default="corpus-campaign")
ap.add_argument("--max-docs", type=int, default=700)  # < 768 proven, margin under 1h cap
ap.add_argument("--profile", default="prompt-profiles/au-register.yaml")
ap.add_argument("--prefix", default="camp",
                help="sub-shard name prefix; use a distinct one per rung to avoid "
                     "bucket-name collisions (e.g. --prefix s5 -> s5-0, s5-1, ...)")
args = ap.parse_args()

# Gather all remaining docs (preserve the ladder's shuffle order within each rung).
docs: dict[str, str] = {}
for rung in args.rungs:
    p = Path(args.src) / rung / "raw" / "documents.json"
    d = json.load(open(p))
    docs.update(d)
    print(f"{rung}: {len(d)} docs")

items = list(docs.items())
n = len(items)
n_shards = math.ceil(n / args.max_docs)
per = math.ceil(n / n_shards)
print(f"\ntotal remaining: {n} docs -> {n_shards} sub-shards of ~{per} (<= {args.max_docs})")

out = Path(args.out)
if out.exists():
    shutil.rmtree(out)
names = []
for i in range(n_shards):
    chunk = dict(items[i * per : (i + 1) * per])
    name = f"{args.prefix}-{i}"
    raw = out / name / "raw"
    raw.mkdir(parents=True)
    json.dump(chunk, open(raw / "documents.json", "w"), ensure_ascii=False, indent=1)
    shutil.copyfile(args.profile, raw / "prompts.yaml")
    names.append((name, len(chunk)))

print("\nsub-shards:")
for name, c in names:
    print(f"  {name}: {c} docs")
print(f'\nextractor_datasets = {json.dumps([nm for nm, _ in names])}')
