"""Prepare the modern-slavery-register corpus for gfmrag extraction.

Reads corpus/all-statements_*.csv and renders each statement row into the
register-style passage format validated in corpus-tuples/smoke-test-2026-06-10.md,
then round-robins the passages into N shards laid out the way gfmrag expects
(docs/workflow/data_format.md):

    <out>/shard-N/raw/documents.json      # {title: passage, ...}

Stdlib only. Usage:

    python scripts/prepare_corpus_shards.py                  # full corpus, 4 shards
    python scripts/prepare_corpus_shards.py --limit 40       # smoke run
    python scripts/prepare_corpus_shards.py --shards 8 --out tmp/corpus-shards
"""

import argparse
import csv
import json
import re
from pathlib import Path

# "NAME (77 159 767 843), NAME (88 000 014 675)" — split on the closing paren,
# not on commas (entity names may contain commas).
_ENTITY_SPLIT = re.compile(r"\)\s*,\s*")


def clean(field: str) -> str:
    """Collapse embedded newlines/whitespace in CSV fields."""
    return " ".join((field or "").split())


def parse_entities(reporting_entities: str) -> list[str]:
    """'A (11 222), B (33 444)' -> ['A (ABN 11 222)', 'B (ABN 33 444)']."""
    text = clean(reporting_entities)
    if not text:
        return []
    parts = _ENTITY_SPLIT.split(text)
    entities = []
    for part in parts:
        part = part.strip().rstrip(",")
        if not part:
            continue
        if not part.endswith(")"):
            part += ")"
        # Label the number as an ABN so the extractor links it correctly.
        entities.append(re.sub(r"\((\d[\d ]*\d)\)$", r"(ABN \1)", part))
    return entities


def join_names(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def build_passage(row: dict) -> tuple[str, str] | None:
    """Render one register row into (title, passage). None if unusable."""
    entities = parse_entities(row.get("ReportingEntities", ""))
    if not entities:
        return None

    idx = clean(row.get("IDX", ""))
    stmt_type = clean(row.get("Type", "")).lower() or "modern slavery"
    start, end = clean(row.get("PeriodStart", "")), clean(row.get("PeriodEnd", ""))
    hq = clean(row.get("HeadquarteredCountries", ""))
    revenue = clean(row.get("AnnualRevenue", ""))
    sectors = clean(row.get("IndustrySectors", ""))
    included = clean(row.get("IncludedEntities", ""))
    link = clean(row.get("Link", ""))

    plural = len(entities) > 1
    sentences = [
        f"{join_names(entities)} filed a {stmt_type} modern slavery statement "
        f"with the Australian Modern Slavery Register for the reporting period "
        f"{start} to {end}."
    ]
    if hq:
        sentences.append(
            f"The reporting entit{'ies are' if plural else 'y is'} headquartered in {hq}."
        )
    if revenue:
        sentences.append(
            f"The reporting entit{'ies have' if plural else 'y has'} an annual "
            f"revenue band of {revenue}."
        )
    if sectors:
        sentences.append(
            f"The reporting entit{'ies operate' if plural else 'y operates'} in the "
            f"industry sectors: {sectors}."
        )
    if included:
        sentences.append(f"The statement also covers the included entities: {included}.")
    if link:
        sentences.append(f"Register entry: {link}.")

    # Short, unique, entity-bearing title (it is prepended to the passage
    # before extraction).
    bare_names = [re.sub(r"\s*\(ABN [\d ]+\)$", "", e) for e in entities[:3]]
    suffix = " et al." if len(entities) > 3 else ""
    title = f"Modern slavery statement {idx}: {' & '.join(bare_names)}{suffix}"
    return title, " ".join(sentences)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", default="corpus/all-statements_2026-04-18.csv", type=Path
    )
    parser.add_argument("--out", default=Path("tmp/corpus-shards"), type=Path)
    parser.add_argument("--shards", default=4, type=int)
    parser.add_argument("--limit", default=None, type=int, help="cap rows (smoke runs)")
    args = parser.parse_args()

    shards: list[dict[str, str]] = [{} for _ in range(args.shards)]
    rows = skipped = 0

    with open(args.input, newline="", encoding="utf-8-sig") as fin:
        for row in csv.DictReader(fin):
            if args.limit is not None and rows - skipped >= args.limit:
                break
            rows += 1
            result = build_passage(row)
            if result is None:
                skipped += 1
                continue
            title, passage = result
            shard = shards[(rows - skipped - 1) % args.shards]
            if title in shard:  # defensive: register IDX should be unique
                title = f"{title} ({rows})"
            shard[title] = passage

    for i, docs in enumerate(shards):
        raw_dir = args.out / f"shard-{i}" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        with open(raw_dir / "documents.json", "w", encoding="utf-8") as fout:
            json.dump(docs, fout, ensure_ascii=False, indent=1)
        print(f"shard-{i}: {len(docs)} documents -> {raw_dir / 'documents.json'}")

    print(f"\n{rows} rows read, {skipped} skipped (no reporting entities).")
    sample_title = next(iter(shards[0]), None)
    if sample_title:
        print(f"\nSample:\n  {sample_title}\n  {shards[0][sample_title][:300]}...")


if __name__ == "__main__":
    main()
