# GFM-RAG for the Australian Modern Slavery Register

This repository adapts **GFM-RAG** (a Graph Foundation Model for Retrieval-Augmented
Generation) into a domain knowledge-graph system over the **Australian Modern Slavery
Register**, built for supply-chain and cyber-insurance risk analysis across Australian
companies.

The upstream project and its general design are documented in
[`README/ABOUT GFM-RAG.md`](README/ABOUT%20GFM-RAG.md). This file describes what is
*different* here.

## The core adaptation: the ABN is the primary key

The single most important change from generic GFM-RAG is that the **Australian Business
Number (ABN)** is treated as the **canonical primary key for every reporting entity**.

Generic GFM-RAG links entities by fuzzy text similarity (ColBERT over surface forms).
That is fine for prose, but it fragments a corporate register, where the same company
appears under many spellings ("De Bortoli Wines", "DeBortoli WInes", "DE BORTOLI WINES
PTY LTD"). An ABN is an **exact, government-issued, unique identifier** — so we make it
the spine of the graph. This threads through every stage:

1. **Extraction** — a register-specific prompt profile
   ([`prompt-profiles/au-register.yaml`](prompt-profiles/au-register.yaml)) instructs the
   tuple extractor to pull each ABN **verbatim** and emit it first, as an
   `[entity, "has ABN", <number>]` triple. (Local tests lifted ABN recall from ~41–56%
   to ~100% on completed docs.)
2. **Canonicalisation** — [`scripts/eval/canonicalise_abn.py`](scripts/eval/canonicalise_abn.py)
   merges every node that shares an ABN into one canonical entity, collapsing surface-form
   variants that text linking leaves split.
3. **Fact-gating** — because ABNs are exact-match keys, every fact in a generated answer
   (company name, claimed relationship) can be **programmatically verified** against the
   register before it reaches a downstream use (e.g. outbound marketing). An ABN either
   matches the register or it does not.

## Pipeline

```
register CSV ──► shards ──► NER + OpenIE ──► per-shard KG ──► union (mother graph)
 (corpus/)    (prepare_*)  (au-register      (stage-1 CSVs)   (merge_union.py)
                            prompt profile)                          │
                                                                     ▼
        retrieval  ◄── stage-2 embeddings ◄── prune ◄── canonicalise by ABN
   (GFM / G-Reasoner GNN +   (graph.pt)    (prune_       (canonicalise_abn.py)
    document retrieval +                    equivalent.py)
    edge traversal)
```

Retrieval favours **document retrieval + edge traversal** over the raw GNN entity-ranking
path, which exhibits degree bias on this corpus (see `notes/`).

## Repository layout (this branch, `dev`)

`dev` carries only the **unionised data and products** plus source and tooling; all
per-shard inputs/sources/products are archived on the
**`slavery-register-source-shards`** branch.

| Path | What |
|---|---|
| `corpus-shards/union-0-5-canon-eq/` | **the final graph** — ABN-canonicalised, equivalence-pruned stage-1 (nodes / edges / relations) |
| `corpus-shards/union-0-5/` | union doc set (`raw/documents.json`) + the built stage-2 `graph.pt` |
| `gfmrag/` | the GFM-RAG package (extraction, retriever, models) |
| `scripts/` | sharding (`prepare_corpus_shards.py`, `prepare_campaign_shards.py`), merge/canonicalise/prune (`scripts/eval/`), and the MCP server (`scripts/mcp/`) — **kept for future corpora** |
| `prompt-profiles/au-register.yaml` | the register-specific extraction prompt profile |
| `deploy/` | Terraform + Docker + serving (GKE and Cloud Run variants) |
| `.mcp.json` | wires the GFM-RAG knowledge graph into Claude as MCP tools (`gfm_retrieve` / `gfm_answer` / `gfm_status`) |
| `README/` | operational + design docs (local/cloud setup, extractor prompts, fact-gating, campaigns) |
| `notes/` | strategy and decision notes |

## Purpose

Crawl and structure intelligence about the top Australian companies to infer
supply-chain dependencies and cyber-security posture — feeding insurance risk
underwriting and targeted marketing. The register is the structured seed; the graph
makes multi-hop relationships (joint filings, group structure, shared dependencies)
queryable.

## Getting started

- Run the knowledge graph locally and query it: [`README/LOCAL SETUP.md`](README/LOCAL%20SETUP.md)
- Cloud deployment: [`README/CLOUD RUN SETUP.md`](README/CLOUD%20RUN%20SETUP.md)
- Extraction prompt profiles: [`README/EXTRACTOR PROMPTS .md`](README/EXTRACTOR%20PROMPTS%20.md)
- Verifying generated facts: [`README/FACT GATING FOR STRUCTURED DATA.md`](README/FACT%20GATING%20FOR%20STRUCTURED%20DATA.md)
- Upstream GFM-RAG: [`README/ABOUT GFM-RAG.md`](README/ABOUT%20GFM-RAG.md)
