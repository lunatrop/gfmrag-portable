#!/usr/bin/env python3
"""Phase-1 step 2: prune the spurious `equivalent` synonym augmentation.

GFM-RAG stage-1 connects each node to ~top-99 cosine neighbours with an
`equivalent` edge (no score). At union scale this fuses *attribute literals*
(revenue bands, reporting periods, "australia", sectors, ABNs) into mega-
cliques that over-smooth the GNN and flood entity retrieval. This is the 84%-
of-edges hub driver diagnosed in the union A/B.

Prune rule (deterministic):
  1. LITERAL nodes = every node that appears as the TARGET of an attribute
     relation (has revenue band, covers reporting period, headquartered in,
     operates in sector, has abn/abn, register entry, has annual revenue band).
  2. Drop any `equivalent` edge with a literal endpoint -> kills band/period/
     location cliques while keeping company<->company synonyms.
  3. Cap the remaining (company) `equivalent` edges to top-K per source node
     (keep-first; no scores exist to rank by) -> kills dense synonym cliques.

Reads  corpus-shards/<SRC>/processed/stage1/{nodes,edges,relations}.csv
Writes corpus-shards/<DST>/processed/stage1/{...}; nodes/relations copied as-is.
Leaves <SRC> intact. See notes/canonicalisation-phase.org.
"""
import csv, os, sys, collections

csv.field_size_limit(1 << 24)
SRC = sys.argv[1] if len(sys.argv) > 1 else "union-0-5-canon"
DST = sys.argv[2] if len(sys.argv) > 2 else "union-0-5-canon-eq"
CAP = int(sys.argv[3]) if len(sys.argv) > 3 else 10
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(ROOT, "corpus-shards", SRC, "processed", "stage1")
DST_DIR = os.path.join(ROOT, "corpus-shards", DST, "processed", "stage1")
os.makedirs(DST_DIR, exist_ok=True)

ATTR_RELS = {
    "has revenue band", "has annual revenue band", "covers reporting period",
    "headquartered in", "operates in sector", "has abn", "abn", "register entry",
}

# ---- pass 1: collect literal nodes (targets of attribute relations) ----------
literals = set()
with open(os.path.join(SRC_DIR, "edges.csv"), newline="") as f:
    r = csv.reader(f); next(r)
    for row in r:
        if len(row) >= 3 and row[1] in ATTR_RELS:
            literals.add(row[2])
print(f"[prune] literal nodes (attribute targets): {len(literals)}", flush=True)

# ---- pass 2: rewrite edges ---------------------------------------------------
eq_in = eq_literal_dropped = eq_capped = eq_kept = other = 0
percap = collections.Counter()
with open(os.path.join(SRC_DIR, "edges.csv"), newline="") as fin, \
     open(os.path.join(DST_DIR, "edges.csv"), "w", newline="") as fout:
    r = csv.reader(fin); w = csv.writer(fout)
    w.writerow(next(r))
    for row in r:
        if len(row) < 3:
            continue
        if row[1] != "equivalent":
            other += 1
            w.writerow(row)
            continue
        eq_in += 1
        s, t = row[0], row[2]
        if s in literals or t in literals:
            eq_literal_dropped += 1
            continue
        if percap[s] >= CAP:
            eq_capped += 1
            continue
        percap[s] += 1
        eq_kept += 1
        w.writerow(row)

# ---- copy nodes + relations unchanged ----------------------------------------
for fn in ("nodes.csv", "relations.csv"):
    with open(os.path.join(SRC_DIR, fn), newline="") as fin, \
         open(os.path.join(DST_DIR, fn), "w", newline="") as fout:
        fout.write(fin.read())

print(f"[prune] equivalent edges in:            {eq_in}", flush=True)
print(f"[prune]   dropped (literal endpoint):   {eq_literal_dropped}", flush=True)
print(f"[prune]   dropped (>top-{CAP} per node):  {eq_capped}", flush=True)
print(f"[prune]   kept (company synonyms):      {eq_kept}", flush=True)
print(f"[prune] non-equivalent edges (kept):    {other}", flush=True)
print(f"[prune] total edges out:                {eq_kept + other}", flush=True)
print(f"[prune] wrote {DST_DIR}", flush=True)
