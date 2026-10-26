#!/usr/bin/env python3
"""Phase-0 canonicalisation: deterministic ABN-merge over union stage-1.

Reads  corpus-shards/<SRC>/processed/stage1/{nodes,edges,relations}.csv
Writes corpus-shards/<DST>/processed/stage1/{nodes,edges,relations}.csv

Rule: two entity surface forms sharing the SAME valid 11-digit ABN are the
same legal entity -> merge into one canonical node, remap every edge onto it,
drop self-loops and duplicate triples created by the collapse. Leaves <SRC>
untouched so the merge is fully revertable.
"""
from __future__ import annotations

import collections
import csv
import os
import re
import sys
from typing import Dict, Iterable, Optional, Set, Tuple

csv.field_size_limit(1 << 24)

ABN_RELS = {"has abn", "abn"}
# Official Australian Taxation Office (ATO) Modulus-89 weights
ABN_WEIGHTS = (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19)


def norm_abn(s: str | None) -> str | None:
    """Extract digits; return string iff exactly 11 digits."""
    d = re.sub(r"\D", "", s or "")
    return d if len(d) == 11 else None


def validate_abn_checksum(abn_digits: str) -> bool:
    """Validate an 11-digit ABN using the official ATO Modulus-89 algorithm.

    Algorithm:
    1. Subtract 1 from the first digit.
    2. Multiply each digit by its positional weight:
       [10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19]
    3. Sum the products.
    4. The total must be evenly divisible by 89 (sum % 89 == 0).
    """
    if not isinstance(abn_digits, str) or len(abn_digits) != 11 or not abn_digits.isdigit():
        return False

    first_digit = int(abn_digits[0]) - 1
    total = first_digit * ABN_WEIGHTS[0]
    for i in range(1, 11):
        total += int(abn_digits[i]) * ABN_WEIGHTS[i]

    return (total % 89) == 0


def is_valid_abn(s: str | None, check_checksum: bool = True) -> bool:
    """Return True if the string normalises to an 11-digit ABN and optionally satisfies checksum."""
    digits = norm_abn(s)
    if not digits:
        return False
    if check_checksum:
        return validate_abn_checksum(digits)
    return True


def build_canonical_map(
    edges_iter: Iterable[Tuple[str, str, str]],
    abn_rels: Set[str] = ABN_RELS,
    validate_checksum: bool = False,
) -> Tuple[Dict[str, str], collections.Counter, int, int]:
    """Scan edges and return (canon_map, name_freq, num_abns, conflicts).

    canon_map: variant_name -> canonical_name
    name_freq: name -> total edge endpoint frequency
    """
    name_abns = collections.defaultdict(set)
    name_freq = collections.Counter()

    for row in edges_iter:
        if len(row) < 3:
            continue
        src, rel, tgt = row[0], row[1], row[2]
        name_freq[src] += 1
        name_freq[tgt] += 1

        rel_lower = rel.strip().lower()
        if rel_lower in abn_rels:
            abn = norm_abn(tgt)
            if abn:
                if not validate_checksum or validate_abn_checksum(abn):
                    name_abns[src].add(abn)

    # Exclude surface forms carrying >1 distinct valid ABN (ambiguous extraction)
    abn_names = collections.defaultdict(set)
    conflicts = 0
    for name, abns in name_abns.items():
        if len(abns) == 1:
            abn_names[next(iter(abns))].add(name)
        else:
            conflicts += 1

    canon: Dict[str, str] = {}
    groups_merged = 0
    for abn, names in abn_names.items():
        if len(names) < 2:
            continue  # singleton ABN: nothing to merge
        groups_merged += 1
        # Canonical choice: most frequent surface form, tie-break longest, then alphabetical
        chosen = sorted(names, key=lambda n: (-name_freq[n], -len(n), n))[0]
        for n in names:
            if n != chosen:
                canon[n] = chosen

    return canon, name_freq, len(abn_names), conflicts


def canonicalise_dataset(
    src_dir: str,
    dst_dir: str,
    validate_checksum: bool = False,
) -> Dict[str, int]:
    """Run full canonicalisation pipeline on nodes, edges, relations."""
    os.makedirs(dst_dir, exist_ok=True)

    # Pass 1: read edges to build canon map
    n_edges_in = 0

    def edge_generator():
        nonlocal n_edges_in
        with open(os.path.join(src_dir, "edges.csv"), newline="", encoding="utf-8") as f:
            r = csv.reader(f)
            _ = next(r, None)
            for row in r:
                n_edges_in += 1
                yield row

    canon, name_freq, n_abns, conflicts = build_canonical_map(
        edge_generator(), validate_checksum=validate_checksum
    )

    def remap(n: str) -> str:
        return canon.get(n, n)

    # Rewrite nodes.csv
    n_nodes_in = n_nodes_out = 0
    seen_nodes = set()
    with open(os.path.join(src_dir, "nodes.csv"), newline="", encoding="utf-8") as fin, \
         open(os.path.join(dst_dir, "nodes.csv"), "w", newline="", encoding="utf-8") as fout:
        r = csv.reader(fin)
        w = csv.writer(fout)
        header = next(r, None)
        if header:
            w.writerow(header)
        for row in r:
            n_nodes_in += 1
            row[0] = remap(row[0])
            if row[0] in seen_nodes:
                continue
            seen_nodes.add(row[0])
            w.writerow(row)
            n_nodes_out += 1

    # Rewrite edges.csv
    n_edges_out = n_selfloop = n_dup = 0
    seen_edges = set()
    with open(os.path.join(src_dir, "edges.csv"), newline="", encoding="utf-8") as fin, \
         open(os.path.join(dst_dir, "edges.csv"), "w", newline="", encoding="utf-8") as fout:
        r = csv.reader(fin)
        w = csv.writer(fout)
        header = next(r, None)
        if header:
            w.writerow(header)
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

    # Copy relations.csv unchanged
    with open(os.path.join(src_dir, "relations.csv"), newline="", encoding="utf-8") as fin, \
         open(os.path.join(dst_dir, "relations.csv"), "w", newline="", encoding="utf-8") as fout:
        fout.write(fin.read())

    return {
        "abns_seen": n_abns,
        "variants_folded": len(canon),
        "conflicts": conflicts,
        "nodes_in": n_nodes_in,
        "nodes_out": n_nodes_out,
        "edges_in": n_edges_in,
        "edges_out": n_edges_out,
        "self_loops_dropped": n_selfloop,
        "duplicates_dropped": n_dup,
    }


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else "union-0-5"
    dst = sys.argv[2] if len(sys.argv) > 2 else "union-0-5-canon"
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    src_dir = os.path.join(root, "corpus-shards", src, "processed", "stage1")
    dst_dir = os.path.join(root, "corpus-shards", dst, "processed", "stage1")

    print(f"[canon] Running canonicalisation: {src} -> {dst}")
    stats = canonicalise_dataset(src_dir, dst_dir)
    print(f"[canon] ABNs seen: {stats['abns_seen']}")
    print(f"[canon] Surface forms folded: {stats['variants_folded']}")
    print(f"[canon] Nodes: {stats['nodes_in']} -> {stats['nodes_out']} (collapsed {stats['nodes_in'] - stats['nodes_out']})")
    print(f"[canon] Edges: {stats['edges_in']} -> {stats['edges_out']} (dropped {stats['self_loops_dropped']} self-loops, {stats['duplicates_dropped']} dups)")
    print(f"[canon] Wrote: {dst_dir}")


if __name__ == "__main__":
    main()
