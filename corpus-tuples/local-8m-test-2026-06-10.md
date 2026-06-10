# Local end-to-end test — GFM-RAG-8M over shard-0 (2026-06-10)

Full pipeline on the WSL box, zero cloud cost: local stage-1 mint (qwen2.5:3b
via Ollama) → stage-2 self-build (mpnet, CPU) → ColBERT EL → GFM-RAG-8M graph
reasoning. Retriever loads in ~6s warm (1.1 min cold incl. stage-2 build).

## Golden query results (top-3, `retrieve(q, top_k=3)`)

**Q1: "Which entity is included in NICK SCALI LIMITED's modern slavery statement?"**
| Rank | Score | Document |
|---|---|---|
| **1** | **7.42** | ✅ **2025-3467: NICK SCALI LIMITED** (contains Plush-Think Sofas) |
| 2 | 3.83 | 2022-2012: Dental Health Services Victoria |
| 3 | 3.83 | 2021-3693: Adelaide Airport |

**Q2: "Which companies headquartered in New Zealand filed a joint modern slavery statement?"**
| Rank | Score | Document |
|---|---|---|
| **1** | **12.25** | ✅ **2022-2432: a2 Milk group joint statement** (only NZ-HQ doc in shard) |
| 2 | 2.58 | 2021-3693: Adelaide Airport |
| 3 | 2.25 | 2022-754: Societe Generale |

Both correct at rank 1 with 2–5× score margins. Control comparison: with NER
broken (entity-less fallback), rankings were degenerate (same top doc for both
queries) — entity seeding is what makes the graph reasoning work.

## Code fixes required (query-time path, ollama backend)

All in `gfmrag/graph_index_construction/ner_model/llm_ner_model.py`:
1. `ChatOllamaNoThink` added to the ollama isinstance branch (was falling into
   the OpenAI-shaped branch → `response_metadata` AttributeError).
2. Bare-list NER responses normalized; dict results no longer fed to `eval()`.
3. **Single-turn explicit prompt for local models**: qwen2.5:3b answers (or
   refuses) the multi-turn one-shot NER format instead of extracting; an
   explicit single instruction extracts perfectly. OpenAI path unchanged.

## Follow-up for the cloud deployment

The vLLM/7B production path uses the *unchanged* multi-turn prompt via the
`openai` branch. Add a query-NER check to the Phase-2 deployment tests to
verify the 7B follows it (the 3B did not).

## Serving layer (`deploy/serve/app.py`, local uvicorn :8001) — PASS

Env: `LLM_API=ollama`, `OPENAI_BASE_URL=http://127.0.0.1:11434/v1` (answers via
Ollama's OpenAI-compatible endpoint). Healthy in 55s.

- `/retrieve` (17s): Nick Scali statement rank 1 (7.42), same as direct test.
- `/answer` (28s): **"PLUSH-THINK SOFAS PTY LTD is included in NICK SCALI
  LIMITED's modern slavery statement."** — correct, grounded, exact-match
  entity name. The full lead-gen QA loop works locally end-to-end.

34M comparison: see `local-34m-test-2026-06-10.md` (8M 2/2 vs 34M 1/2 at this
scale). Pending: rung-1 cloud run (gated on GPUS_ALL_REGIONS quota grant).
