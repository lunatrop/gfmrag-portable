# Taxonomy normalization A/B — shard-0, 8M checkpoint (2026-06-11)

`scripts/anti-slavery-register-shard-maker.py` folds the 47 raw register sector
strings to 12 canonical TautSec labels (2 unmapped strings corpus-wide kept
verbatim). Normalized graph: 147 nodes / 721 edges / 58 relations
(vs 124/528/42 raw). Same shard membership, seed 42.

## "Which companies operate in healthcare?" (top-4)

| Rank | Normalized graph | Original graph |
|---|---|---|
| 1 | Husqvarna 3.50 ❌ | Societe Generale 5.50 ❌ |
| 2 | Societe Generale 1.33 ❌ | Adelaide Airport 4.83 ❌ |
| 3 | Adelaide Airport 1.00 ❌ | **Dental Health 3.83** ✅ |
| 4 | Richland Express 1.00 ❌ | **Eye & Ear Hospital 2.58** ✅ |

Both healthcare companies dropped OUT of the top-4 on the normalized graph.

## Golden-query regression (normalized graph) — both still pass

- Nick Scali → rank 1, **7.75** (vs 7.42 raw — slightly better)
- a2 Milk NZ joint → rank 1, **9.20**

## Why normalization didn't fix the concept query

The query "Which companies operate in healthcare?" contains **no named
entities** — strict query-NER correctly returns `[]` (deterministic, verified),
so retrieval falls back to entity-linking the whole query string. That
fallback is where the ranking is decided, and counter-intuitively the RAW
sector strings give ColBERT more lexical surface ("healthcare and
pharmaceuticals" ≈ query word) than the consolidated graph does. The
normalization is good graph hygiene (richer graph, golden queries unharmed or
better) but it cannot help a query that never produces a seed.

**The actual gap: concept-query seeding.** Options, in rough order of merit:
1. Bigger query-NER model — the 7B should extract "healthcare" as a topic term
   (the 3B is prompt-fragile: three rewordings to add topic terms all
   collapsed it to permanent `[]`; the working prompt is frozen-by-test).
2. EL fallback tuning — link salient query n-grams rather than the whole
   sentence.
3. Hub suppression remains open (generic `modern slavery statement` node,
   degree 14) — it dominates whenever seeding fails.

## Environment lesson (cost a full debugging cycle)

Ollama 0.30.6 auto-enabled the **Vulkan backend** on the GTX 960M after a
server restart → silently degraded generation (all NER → `[]`, deterministic).
`OLLAMA_VULKAN=false` is mandatory on this box. Also: CUDA needs Windows
driver ≥570 (have 556), so Ollama is CPU-only either way — all local timings
reflect CPU inference.
