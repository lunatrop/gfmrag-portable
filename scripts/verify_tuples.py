"""Fact-verification gate: validate extracted tuples against the register.

The corpus is generated from structured CSV, so ground truth is free. For every
document in a shard, check that the extraction preserved the register facts
(entity names, ABNs, revenue band, reporting period, HQ, sectors) and flag
entity-looking nodes that match NO register entity (LLM typos — the
WOOLWORTHHS class). Required before any lead-gen use of the tuples
(corpus-tuples/smoke-test-2026-06-10.md, finding 2).

Usage:
    python scripts/verify_tuples.py --shard corpus-tuples/shard-0 \
        --documents corpus-shards/shard-0/raw/documents.json
"""

import argparse
import csv
import json
import re
from pathlib import Path

IDX_RE = re.compile(r"Modern slavery statement (\S+):")


def norm(s: str) -> str:
    """Match the extractor's normalisation: lowercase, punctuation to spaces."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())


def parse_entity_names(reporting_entities: str) -> list[str]:
    """Names only, ABN parentheticals stripped."""
    parts = re.split(r"\)\s*,\s*", reporting_entities or "")
    names = []
    for p in parts:
        p = re.sub(r"\(\s*[\d\s]+$", "", p.strip().rstrip(",")).strip()
        p = re.sub(r"\([\d\s]+\)$", "", p).strip()
        if p:
            names.append(p)
    return names


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shard", type=Path, required=True, help="dir with nodes/edges.csv")
    ap.add_argument("--documents", type=Path, required=True, help="raw/documents.json")
    ap.add_argument("--register", type=Path, default="corpus/all-statements_2026-04-18.csv")
    args = ap.parse_args()

    register = {}
    with open(args.register, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            register[row["IDX"].strip()] = row

    titles = json.load(open(args.documents))
    docs = {m.group(1): t for t in titles if (m := IDX_RE.match(t))}

    with open(args.shard / "nodes.csv", newline="", encoding="utf-8") as f:
        nodes = [r for r in csv.DictReader(f)]
    with open(args.shard / "edges.csv", newline="", encoding="utf-8") as f:
        edges = [r for r in csv.DictReader(f)]

    node_names = {norm(n["name"]) for n in nodes}
    edge_text = " | ".join(
        norm(f"{e['source']} {e['relation']} {e['target']}") for e in edges
    )
    haystack = " | ".join(node_names) + " | " + edge_text

    checks = {k: [0, 0] for k in ("entity", "abn", "revenue", "period", "hq", "sector")}
    failures = []

    def check(kind: str, idx: str, needle: str, found: bool) -> None:
        checks[kind][1] += 1
        if found:
            checks[kind][0] += 1
        else:
            failures.append(f"{kind:8} {idx}: missing {needle!r}")

    for idx in docs:
        row = register.get(idx)
        if row is None:
            failures.append(f"doc      {idx}: not in register CSV")
            continue
        for name in parse_entity_names(row["ReportingEntities"]):
            check("entity", idx, name, norm(name) in haystack)
        for abn in re.findall(r"\d{11}", (row.get("ABN") or "").replace(" ", "")):
            spaced = norm(" ".join([abn[:2], abn[2:5], abn[5:8], abn[8:]]))
            check("abn", idx, abn, spaced in haystack or abn in haystack)
        if row.get("AnnualRevenue"):
            check("revenue", idx, row["AnnualRevenue"], norm(row["AnnualRevenue"]) in haystack)
        if row.get("PeriodStart") and row.get("PeriodEnd"):
            period = norm(f"{row['PeriodStart']} to {row['PeriodEnd']}")
            check("period", idx, period, period in haystack)
        if row.get("HeadquarteredCountries"):
            hqs = [h.strip() for h in row["HeadquarteredCountries"].split(",") if h.strip()]
            check("hq", idx, row["HeadquarteredCountries"],
                  any(norm(h) in haystack for h in hqs))
        sectors = [s.strip() for s in (row.get("IndustrySectors") or "").split(",") if s.strip()]
        if sectors:
            check("sector", idx, sectors[0], norm(sectors[0]) in haystack)

    # Reverse check: company-shaped nodes that match no register entity = suspects.
    register_names = {norm(n) for r in register.values()
                      for n in parse_entity_names(r["ReportingEntities"])}
    register_names |= {norm(r.get("IncludedEntities", "")) for r in register.values()}
    company_re = re.compile(r"\b(pty|ltd|limited|holdings|inc|plc|corporation)\b")
    suspects = sorted(
        n["name"] for n in nodes
        if n.get("type") != "document"
        and company_re.search(norm(n["name"]))
        and not any(norm(n["name"]) in rn or rn in norm(n["name"])
                    for rn in register_names if rn)
    )

    print(f"Documents checked: {len(docs)}\n")
    print(f"{'fact':10} {'found':>5} {'expected':>8} {'recall':>8}")
    for kind, (found, total) in checks.items():
        pct = f"{100 * found / total:.0f}%" if total else "n/a"
        print(f"{kind:10} {found:5d} {total:8d} {pct:>8}")

    if failures:
        print(f"\nMISSING FACTS ({len(failures)}):")
        for f_ in failures[:30]:
            print(" ", f_)
    if suspects:
        print(f"\nSUSPECT ENTITY NODES — match no register entity ({len(suspects)}):")
        for s in suspects[:20]:
            print(" ", s)

    total_found = sum(f for f, _ in checks.values())
    total_expected = sum(t for _, t in checks.values())
    print(f"\nOVERALL: {total_found}/{total_expected} facts preserved "
          f"({100 * total_found / max(total_expected, 1):.0f}%), "
          f"{len(suspects)} suspect entities")


if __name__ == "__main__":
    main()
