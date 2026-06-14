#!/usr/bin/env python3
"""Characterise the `equivalent`-edge synonym population in a stage-1 dataset:
per-node equivalent-degree distribution and how much a top-k cap would prune.
Read-only; no writes."""
import csv, os, sys, collections

csv.field_size_limit(1 << 24)
DS = sys.argv[1] if len(sys.argv) > 1 else "union-0-5-canon"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EDGES = os.path.join(ROOT, "corpus-shards", DS, "processed", "stage1", "edges.csv")

deg = collections.Counter()       # node -> #equivalent edges incident (as source)
n_eq = n_tot = 0
with open(EDGES, newline="") as f:
    r = csv.reader(f); next(r)
    for row in r:
        if len(row) < 3:
            continue
        n_tot += 1
        if row[1] == "equivalent":
            n_eq += 1
            deg[row[0]] += 1

degs = sorted(deg.values(), reverse=True)
print(f"dataset            : {DS}")
print(f"total edges        : {n_tot}")
print(f"equivalent edges   : {n_eq}  ({100*n_eq/n_tot:.1f}% of all edges)")
print(f"nodes w/ eq edges  : {len(deg)}")
print(f"max eq-degree      : {degs[0]}")
print(f"mean eq-degree     : {n_eq/len(deg):.1f}")
for p in (0.5, 0.9, 0.99):
    print(f"  p{int(p*100):<3} eq-degree    : {degs[int(len(degs)*(1-p))]}")
for cap in (5, 10, 20, 50):
    kept = sum(min(d, cap) for d in degs)
    print(f"cap k={cap:<3} -> keep {kept:>9} eq edges ({100*kept/n_eq:.1f}%), prune {n_eq-kept}")
