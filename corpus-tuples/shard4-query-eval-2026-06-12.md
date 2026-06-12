# Shard-4 G-Reasoner retrieval evaluation — 12 sophisticated queries (2026-06-12)

Largest indexed shard to date. Evaluates retrieval **speed** and **quality**, and
assesses two business uses: **marketing-lead generation** and **supply-chain
crawler seeding** (extending each ABN with supplier information).

- **Index:** shard-4 = 6 sub-shards (camp-0..5) merged (method-3 exact-name dedup).
- **Size:** 4,096 statements · 22,580 nodes (18,484 entity + 4,096 document) · 489,686 edges · 103 relations.
- **Checkpoint:** rmanluo/G-reasoner-34M, Qwen3-Embedding-0.6B (fingerprint `71345f28…`).
- **Served by:** Cloud Run QA service (L4), built at `GFMRAG_EMB_BATCH_SIZE=8`.
- **Endpoint:** `POST /retrieve` (`top_k=8`, `target_types=["entity","document"]`).

---

## 1. Retrieval speed

| Metric | Steady-state `/retrieve` |
|---|---|
| Mean | **1.09 s** |
| Median | 1.06 s |
| Min / Max | 0.92 s / 1.45 s |
| p90 | 1.24 s |
| One-time ColBERT index build (warmup, 22.5k entities) | ~290 s |
| Cold-start from scale-to-zero (image + model + graph.pt load) | ~13 min |

~1 s/query warm — interactive. The 290 s ColBERT build is paid once per warm
instance; afterwards the service keeps scale-to-zero economics. A UI should call
`/warmup` and poll `/ready` before issuing user queries.

---

## 2. The 12 queries and quality scorecard

Scored on whether the **top-3 retrieved statements** are genuinely on-target.

| # | Axis | Query | Rank-1 result | Verdict |
|---|---|---|---|---|
| 1 | multi-hop | Companies that filed a joint modern slavery statement together with another reporting entity | GSFM RE Services (multi-fund filer) | ✅ hit |
| 2 | multi-hop | Subsidiaries and entities included within a parent company's group modern slavery statement | Transport Asset Holding (1bn, govt group) | ✅ hit |
| 3 | multi-hop | Mining, metals and resources companies headquartered outside Australia | Air NZ (NZ), Camelot UK Bidco | ◐ partial |
| 4 | segment | Financial, insurance and real estate companies that filed statements | CIBC, Norinchukin | ✅ hit |
| 5 | segment | Reporting entities with annual revenue of one billion dollars or more | Nationwide News, Lynas, CIBC | ✅ hit |
| 6 | segment | Reporting entities headquartered in the United States | Rural Press (AU), Ricoh (JP) | ✗ weak |
| 7 | lead | Large Australian retail and consumer goods companies — prospects for compliance software | Global Retail Brands Australia | ✅ hit |
| 8 | lead | High-revenue manufacturing and industrial companies with complex global operations | MAAS Group (AU+Indonesia) | ✅ hit |
| 9 | lead | Food, beverage and agriculture companies that source goods internationally | Reject Shop, IKEA, Chrisco | ✅ strong |
| 10 | crawl | Importers and logistics companies whose supply chains span multiple countries | Aus Grain Export, Bitumen Importers, Louis Dreyfus | ✅ strong |
| 11 | crawl | Textiles, apparel and consumer goods companies in high-risk sectors to map suppliers for | Active Apparel Group (sector=fashion/textiles) | ✅ hit |
| 12 | crawl | Large mining and resources entities suitable for tier-one supplier mapping and ABN enrichment | ABN Group (construction — lexical collision) | ✗ weak |

**~9/12 strong, 1 partial, 2 weak (≈75–83%)** — strong for an *inductive* graph
index with **zero tuning**, queried in plain English.

---

## 3. Key structural finding: document vs. entity retrieval

- **Document (statement) retrieval is production-grade.** Top statements are
  on-target and resolve to clean company records.
- **Entity retrieval is noisy** — a few **hub nodes** dominate nearly every query
  (`the trustee for think tank commercial w04 trust`, the recurring ABN
  `46 061 711 804`, the `pharos aq …` series, raw URL and relation nodes).
- **Cause:** the **401,376 `equivalent` edges** from the cosine-similarity
  entity-linking augmentation create high-degree hubs that the GNN diffuses score
  into regardless of query.
- **Weak spots:** geography-only queries (US-HQ, Q6 — too few US-HQ entities to
  isolate) and queries with jargon tokens that collide with company names
  (Q12 "ABN" → matched *ABN Group Pty Ltd*).

---

## 4. Marketing-lead value — strong, with the right pattern

Document retrieval + graph enrichment yields **ready-to-use lead cards**
(company → ABN, sector, revenue band, HQ). Real cards produced this run:

```
Food/bev importers:  THE REJECT SHOP   ABN 33 006 122 676  rev 800–900m  AU  food&bev/agri
                     IKEA PTY LIMITED   ABN 84 006 270 757  rev 1bn       AU  food&bev/agri
                     CHRISCO HAMPERS    ABN 41 080 852 535  rev 100–150m  AU  food&bev/agri
Retail/consumer:     GLOBAL RETAIL BRANDS AUSTRALIA  ABN 74 323 352 189  rev 200–250m  AU
Manufacturing:       MAAS GROUP HOLDINGS LIMITED     ABN 84 632 994 542  rev 250–300m  AU+Indonesia
Textiles/apparel:    ACTIVE APPAREL GROUP            (ABN in statement)   rev 250–300m  AU  fashion/textiles
```

**Best-practice lead query shape:** `<sector> + <scale/revenue> + <geography>` in
natural language; read the **`document`** results; enrich via the graph. ICP
slices the index supports directly: sector (financial 638 / mining 470 /
construction 388 / food-agri 379 / transport 299 / IT 241 / healthcare 231),
revenue band, and HQ country. Each lead row carries an ABN for CRM matching.

---

## 5. Supply-chain crawler seeding (ABN enrichment) — high value, honest scope

**Not in the index:** supplier-level data (who supplies whom, sourcing countries).
The register statements are *metadata*, not full supplier disclosures.

**What the index DOES provide — exactly the crawler seed layer:** for any thematic
query you get a prioritised, deduplicated seed set of
`(company, ABN, sector, revenue, HQ, group structure)`:
- **Who to crawl** — ABNs surfaced by risk-relevant queries (apparel, food/agri, importers, mining).
- **How to prioritise** — sector modern-slavery risk × revenue scale × cross-border HQ.
- **Where to expand** — `filed joint … with` (2,834 edges) and `includes entity`
  (6,079) give the **corporate group graph**, so one seed ABN expands to its
  parent/subsidiary/JV ABNs before crawling a single external page.

Q10/Q11 demonstrate it: "importers/logistics" → Australian Grain Export, Bitumen
Importers, Louis Dreyfus (with ABNs); "textiles/apparel" → Active Apparel Group —
each a directly-actionable crawl seed.

---

## 6. Recommendations

1. **Use `document` retrieval (not `entity`) for lead/seed lists**, then enrich via
   the graph. If using entity results, filter by node type.
2. **Suppress hub nodes** — down-weight high-degree synonym hubs, or rebuild
   stage-1 with a tighter `max_sim_neighbors`. *Do this before the 0-4 union* if
   entity-level retrieval is needed; the hub problem grows with scale.
3. **Avoid jargon tokens that collide with company names** (e.g. "ABN") in queries.
4. **Geography filtering is weak via semantic retrieval** — for "HQ = X" use a
   graph/attribute filter on `headquartered in`, not free text.

**Union implication:** a larger index yields more and deeper leads per query (more
multi-hop group structure), but the document-vs-entity gap and hub noise carry
over — so the union is worth building, with hub suppression as the one quality fix
to land first.

---

## 7. `/answer` (LLM synthesis) demos

`/answer` runs the same retrieval, then feeds the top statements to Qwen2.5-3B for
a natural-language answer. Findings (3 demos):

| Demo | Query | Latency (warm) | Outcome |
|---|---|---|---|
| group/joint filings | which entities filed in a group/joint statement | 12.7 s | ✅ strong — listed GSFM RE funds (+ABNs), Enero Group, Salvation Army |
| importers/logistics | importers with multi-country supply chains | 113.6 s | ◐ retrieval good (Grain Export, Bitumen Importers) but 3B wrongly answered "none" |
| food/bev | food/bev intl sourcers | timeout | first call cold-started the vLLM service past the client timeout |

**Takeaways:** `/answer` works and grounds well, but is **12–114 s warm vs ~1 s for
`/retrieve`**, and Qwen2.5-3B synthesis is **hit-or-miss** (good at structured
listing, poor at judgement). For leads / crawler seeding, prefer **`/retrieve` +
graph enrichment**; reserve `/answer` for a narrative layer, ideally with a
stronger generation model.

---

## Appendix — environment

- Per-query raw results: `corpus-tuples/shard4-query-results-2026-06-12.json`.
- Scripts: `scripts/eval/run_queries.py` (retrieval suite),
  `scripts/eval/run_answer.py` (LLM demos), `scripts/eval/enrich.py` (lead cards),
  `scripts/eval/inspect_graph.py` (graph content).
- Build provenance: see [[stage2-build-memory-constraint]] — stage-2 is
  memory-bound (long document-node embedding), fixed via `GFMRAG_EMB_BATCH_SIZE=8`
  on the L4; not the 1h GPU cap.
