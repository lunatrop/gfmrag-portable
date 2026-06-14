#!/usr/bin/env python3
"""Phase-0 canonicalisation: deterministic ABN-merge over union stage-1.

Reads  corpus-shards/<SRC>/processed/stage1/{nodes,edges,relations}.csv
Writes corpus-shards/<DST>/processed/stage1/{nodes,edges,relations}.csv

Rule: two entity surface forms sharing the SAME valid 11-digit ABN are the
same legal entity -> merge into one canonical node, remap every edge onto it,
drop self-loops and duplicate triples created by the collapse. Leaves <SRC>
untouched so the merge is fully revertable.

Out of scope (later phases): fuzzy/no-ABN matching, the MERGE-vs-LINK *link*
side, the persisted canonical store. See notes/canonicalisation-phase.org.
"""
import csv, os, re, sys, collections

csv.field_size_limit(1 << 24)

SRC = sys.argv[1] if len(sys.argv) > 1 else "union-0-5"
DST = sys.argv[2] if len(sys.argv) > 2 else "union-0-5-canon"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(ROOT, "corpus-shards", SRC, "processed", "stage1")
DST_DIR = os.path.join(ROOT, "corpus-shards", DST, "processed", "stage1")
os.makedirs(DST_DIR, exist_ok=True)

ABN_RELS = {"has abn", "abn"}


def norm_abn(s):
    """Digits only; valid iff exactly 11 digits."""
    d = re.sub(r"\D", "", s or "")
    return d if len(d) == 11 else None


# ---- pass 1: collect surface-form -> set(valid ABNs) from edges --------------
name_abns = collections.defaultdict(set)   # entity name -> {abn,...}
name_freq = collections.Counter()          # name -> #edges it appears in (endpoint)
n_edges_in = 0
with open(os.path.join(SRC_DIR, "edges.csv"), newline="") as f:
    r = csv.reader(f)
    header = next(r)
    for row in r:
        if len(row) < 3:
            continue
        n_edges_in += 1
        src, rel, tgt = row[0], row[1], row[2]
        name_freq[src] += 1
        name_freq[tgt] += 1
        if rel in ABN_RELS:
            abn = norm_abn(tgt)
            if abn:
                name_abns[src].add(abn)

# ---- build canonical map -----------------------------------------------------
# Exclude surface forms that carry >1 distinct valid ABN (ambiguous extraction).
abn_names = collections.defaultdict(set)   # abn -> {names with exactly this abn}
conflicts = 0
for name, abns in name_abns.items():
    if len(abns) == 1:
        abn_names[next(iter(abns))].add(name)
    else:
        conflicts += 1

canon = {}            # variant name -> canonical name
groups_merged = 0
for abn, names in abn_names.items():
    if len(names) < 2:
        continue       # singleton ABN: nothing to merge
    groups_merged += 1
    # canonical = most frequent surface form; tie-break longest, then alphabetical
    chosen = sorted(names, key=lambda n: (-name_freq[n], -len(n), n))[0]
    for n in names:
        if n != chosen:
            canon[n] = chosen

print(f"[canon] ABNs seen (valid, single-name-resolved): {len(abn_names)}", flush=True)
print(f"[canon] ABN groups with >1 surface form (merged): {groups_merged}", flush=True)
print(f"[canon] surface forms folded into a canonical:    {len(canon)}", flush=True)
print(f"[canon] surface forms with conflicting ABNs (skipped): {conflicts}", flush=True)


def remap(n):
    return canon.get(n, n)


# ---- rewrite nodes.csv (collapse merged entities) ----------------------------
n_nodes_in = n_nodes_out = 0
seen_nodes = set()
with open(os.path.join(SRC_DIR, "nodes.csv"), newline="") as fin, \
     open(os.path.join(DST_DIR, "nodes.csv"), "w", newline="") as fout:
    r = csv.reader(fin); w = csv.writer(fout)
    w.writerow(next(r))
    for row in r:
        n_nodes_in += 1
        row[0] = remap(row[0])
        if row[0] in seen_nodes:
            continue          # duplicate after collapse -> keep first
        seen_nodes.add(row[0])
        w.writerow(row)
        n_nodes_out += 1

# ---- rewrite edges.csv (remap endpoints, drop self-loops + dup triples) ------
n_edges_out = n_selfloop = n_dup = 0
seen_edges = set()
with open(os.path.join(SRC_DIR, "edges.csv"), newline="") as fin, \
     open(os.path.join(DST_DIR, "edges.csv"), "w", newline="") as fout:
    r = csv.reader(fin); w = csv.writer(fout)
    w.writerow(next(r))
    for row in r:
        if len(row) < 3:
            continue
        s, rel, t = remap(row[0]), row[1], remap(row[2])
        if s == t:
            n_selfloop += 1
            continue
        key = (s, rel, t)
        if key in seen_edges:
            n_dup += 1
            continue
        seen_edges.add(key)
        row[0], row[2] = s, t
        w.writerow(row)
        n_edges_out += 1

# ---- relations.csv unchanged -------------------------------------------------
with open(os.path.join(SRC_DIR, "relations.csv"), newline="") as fin, \
     open(os.path.join(DST_DIR, "relations.csv"), "w", newline="") as fout:
    fout.write(fin.read())

print(f"[canon] nodes: {n_nodes_in} -> {n_nodes_out}  (collapsed {n_nodes_in - n_nodes_out})", flush=True)
print(f"[canon] edges: {n_edges_in} -> {n_edges_out}  (self-loops dropped {n_selfloop}, dup triples dropped {n_dup})", flush=True)
print(f"[canon] wrote {DST_DIR}", flush=True)
