# GFM-RAG Portable (Australian Modern Slavery Register)

> **Provenance & Portability Note**:  
> This repository is derived from the upstream [**GFM-RAG**](https://github.com/RManLuo/gfm-rag) project (Graph Foundation Model for Retrieval-Augmented Generation, NeurIPS '25 / ICLR '26 by Linhao Luo & Zicheng Zhao). It has been adapted into a **portable, standalone implementation** designed for local exploration, reproducible evaluation, and domain-specific knowledge graph indexing over corporate registers. It serves as a companion systems repository alongside exploratory notebook studies (such as the [Colab validation suite](https://github.com/lunatrop/colab)).

---

## What Makes This Fork "Portable"?

The original GFM-RAG framework assumes a generalized academic setup often tied to extensive distributed crawls, remote GPUs, and generic entity linking. This repository refactors and packages the system for high portability:

1. **Self-Contained Knowledge Graph & Indices**:
   - Bundles pre-built, unionized graph structures and embeddings (`corpus-shards/union-0-5-canon-eq/` and `graph.pt`).
   - Allows users to test and query the retriever immediately out-of-the-box without executing a multi-day data crawl or standing up dedicated GPU clusters.

2. **Cross-Platform & Low-Resource Runtime**:
   - Configured with optional backend profiles via Poetry extras (`faiss-cpu` for standard local development on laptops/CPUs vs. `faiss-gpu-cu12` for CUDA-enabled environments).
   - Includes containerized deployment configurations (`deploy/`) for lightweight local or serverless serving (e.g., Cloud Run / GKE).

3. **Native Model Context Protocol (MCP) Integration**:
   - Out-of-the-box MCP server support (`.mcp.json` and `scripts/mcp/`) that exposes graph retrieval and question-answering tools (`gfm_retrieve`, `gfm_answer`, `gfm_status`) directly to AI assistants such as Claude Desktop or IDE agents.

4. **Deterministic Domain Grounding (ABN Primary Key)**:
   - Adapts fuzzy entity extraction into a verifiable, deterministic graph using exact Australian Business Numbers (ABNs) as unique primary keys.

---

## The Core Adaptation: The ABN as Primary Key

Generic GFM-RAG links entities via fuzzy text similarity (ColBERT over surface forms). While suitable for general prose, fuzzy linking fragments corporate registers where entities appear under varying naming conventions (*"De Bortoli Wines"*, *"DeBortoli WInes"*, *"DE BORTOLI WINES PTY LTD"*).

Here, the **Australian Business Number (ABN)** is the canonical primary key for every reporting entity:

1. **Extraction**:
   - A register-specific prompt profile ([`prompt-profiles/au-register.yaml`](prompt-profiles/au-register.yaml)) directs tuple extractors to pull each ABN verbatim and emit it as an `[entity, "has ABN", <number>]` triple.
2. **Canonicalisation**:
   - [`scripts/eval/canonicalise_abn.py`](scripts/eval/canonicalise_abn.py) merges nodes sharing an ABN into a single canonical entity, resolving surface-form variants.
3. **Fact-Gating**:
   - Every fact generated in a downstream answer (company name, reported relationships) can be programmatically validated against official register data before dissemination.

---

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

Retrieval favours **document retrieval + edge traversal** over the raw GNN entity-ranking path, mitigating degree bias on corporate filing corpora.

---

## Repository Layout

* `corpus-shards/union-0-5-canon-eq/`: The final graph — ABN-canonicalised, equivalence-pruned stage-1 (nodes, edges, relations).
* `corpus-shards/union-0-5/`: Union document set (`raw/documents.json`) and the built stage-2 `graph.pt`.
* `gfmrag/`: Core GFM-RAG Python package (extraction, retriever, models).
* `scripts/`: Corpus sharding (`prepare_corpus_shards.py`), merge/canonicalise/prune utilities, and the MCP server (`scripts/mcp/`).
* `prompt-profiles/au-register.yaml`: The register-specific extraction prompt profile.
* `deploy/`: Terraform, Docker, and serving configurations (GKE and Cloud Run variants).
* `.mcp.json`: Wires the GFM-RAG knowledge graph into AI agents as MCP tools.
* `README/`: Operational guides, local/cloud setup walkthroughs, and fact-gating references.
* `notes/`: Architectural notes and benchmarking observations.

---

## Getting Started

- **Local Setup & Querying**: [`README/LOCAL SETUP.md`](README/LOCAL%20SETUP.md)
- **Cloud Deployment**: [`README/CLOUD RUN SETUP.md`](README/CLOUD%20RUN%20SETUP.md)
- **Extraction Prompts**: [`README/EXTRACTOR PROMPTS .md`](README/EXTRACTOR%20PROMPTS%20.md)
- **Fact-Gating Guide**: [`README/FACT GATING FOR STRUCTURED DATA.md`](README/FACT%20GATING%20FOR%20STRUCTURED%20DATA.md)
- **Original Upstream Documentation**: [`README/ABOUT GFM-RAG.md`](README/ABOUT%20GFM-RAG.md)
