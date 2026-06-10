"""Taxonomy-normalising shard maker for the Australian Modern Slavery Register corpus.

Same pipeline as prepare_corpus_shards.py (passage rendering + ladder sharding)
with one change: each statement's raw register sector strings (47 variants) are
normalised to the 12 canonical TautSec sectors via corpus/taxonomy-mapping.json
BEFORE the passage is rendered.

Why: raw sector strings fragment the knowledge graph — e.g. "Healthcare and
pharmaceuticals" and "Health care and social assistance" become two unconnected
entity nodes, so a query seeded with "healthcare" cannot reach half the
healthcare companies (see corpus-tuples/local-8m-test-2026-06-10.md findings).
One canonical label per sector -> one entity node shared by every company in
that sector.

Usage:
    python scripts/anti-slavery-register-shard-maker.py            # -> corpus-shards-normalized/
    python scripts/anti-slavery-register-shard-maker.py --out X --ladder 16,64,rest --seed 42
"""

import argparse
import csv
import json
import random
from pathlib import Path

from prepare_corpus_shards import build_passage, clean

# Human/LLM-friendly canonical sector labels per TautSec code. These become
# graph entity names — phrases a query-NER term like "healthcare" will
# entity-link to, so keep them short, lowercase-friendly and unambiguous.
TAUTSEC_LABELS = {
    "MANU": "manufacturing and resources",
    "PROF": "professional services",
    "FINI": "financial services and insurance",
    "RETH": "retail and hospitality",
    "TRAN": "transport and logistics",
    "HEAL": "healthcare",
    "UTIL": "utilities",
    "TECH": "technology and telecommunications",
    "ENTM": "entertainment and media",
    "OTH": "other industries",
    "EDUC": "education",
    "PUBL": "public administration",
}


def load_sector_map(taxonomy_path: Path) -> dict[str, str]:
    """register sector string (whitespace-collapsed) -> canonical label."""
    mapping = json.loads(taxonomy_path.read_text())["register_to_tautsec"]
    return {
        clean(register_sector): TAUTSEC_LABELS[entry["tautsec_code"]]
        for register_sector, entry in mapping.items()
    }


def normalise_sectors(raw_field: str, sector_map: dict[str, str]) -> tuple[str, int]:
    """Multi-sector register field (newline-separated) -> canonical labels.

    Returns (joined labels deduped in first-seen order, unmapped count).
    Unmapped sectors are kept as-is so no information is silently dropped.
    """
    labels: list[str] = []
    unmapped = 0
    for sector in raw_field.split("\n"):
        sector = clean(sector)
        if not sector:
            continue
        label = sector_map.get(sector)
        if label is None:
            unmapped += 1
            label = sector
        if label not in labels:
            labels.append(label)
    return ", ".join(labels), unmapped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", default="corpus/all-statements_2026-04-18.csv", type=Path
    )
    parser.add_argument(
        "--taxonomy", default="corpus/taxonomy-mapping.json", type=Path
    )
    parser.add_argument("--out", default=Path("corpus-shards-normalized"), type=Path)
    parser.add_argument("--ladder", default="16,64,256,1024,4096,rest")
    parser.add_argument("--seed", default=42, type=int)
    args = parser.parse_args()

    sector_map = load_sector_map(args.taxonomy)

    docs: list[tuple[str, str]] = []
    rows = skipped = unmapped_total = 0
    with open(args.input, newline="", encoding="utf-8-sig") as fin:
        for row in csv.DictReader(fin):
            rows += 1
            normalised, unmapped = normalise_sectors(
                row.get("IndustrySectors") or "", sector_map
            )
            unmapped_total += unmapped
            row = dict(row)
            row["IndustrySectors"] = normalised
            result = build_passage(row)
            if result is None:
                skipped += 1
                continue
            docs.append(result)

    # Identical shuffle + slicing to prepare_corpus_shards exponential mode, so
    # shard membership matches the non-normalised corpus-shards/ run for run.
    random.Random(args.seed).shuffle(docs)
    sizes = []
    parts = args.ladder.split(",")
    for j, part in enumerate(parts):
        if part.strip() == "rest":
            if j != len(parts) - 1:
                parser.error("'rest' must be the last ladder entry")
            sizes.append(len(docs) - sum(sizes))
        else:
            sizes.append(int(part))
    if sum(sizes) > len(docs):
        parser.error(f"ladder sums to {sum(sizes)} but only {len(docs)} documents")

    pos = 0
    for i, size in enumerate(sizes):
        raw_dir = args.out / f"shard-{i}" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        shard = dict(docs[pos : pos + size])
        pos += size
        with open(raw_dir / "documents.json", "w", encoding="utf-8") as fout:
            json.dump(shard, fout, ensure_ascii=False, indent=1)
        print(f"shard-{i}: {len(shard)} documents -> {raw_dir / 'documents.json'}")

    print(
        f"\n{rows} rows read, {skipped} skipped, "
        f"{unmapped_total} unmapped sector strings kept verbatim."
    )


if __name__ == "__main__":
    main()
