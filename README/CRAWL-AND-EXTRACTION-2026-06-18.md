# Crawl & Extraction Report — 2026-06-18

Web-crawl-driven relationship discovery and tuple extraction over the Australian
Modern Slavery Register network, for supply-chain and cyber-insurance marketing
purposes.

## What was done today

### 1. Single-entity crawl (proof of method)
A register entity was picked at random from the lowest revenue band (0–99M):
**RASIER PACIFIC PTY LTD** (an Uber Australia subsidiary). A web crawl found and
**verified** its links to companies already surfaced in the network:
- **Woolworths** — Uber Eats grocery-delivery partner (2021).
- **Deliveroo** — direct Uber Eats competitor (exited AU Nov 2022).
- **PwC** — auditor of parent Uber Technologies.
- Hypothesis **refuted** by the crawl: no Uber–Endeavour delivery link (BWS/Dan
  Murphy's use DoorDash/Menulog) — the adversarial check stopped a false claim.

Extraction → `corpus-tuples-crawled/rasier-pacific-uber.json`.

### 2. Network crawl for cyber-insurance targeting
A 14-company multi-agent web crawl (network hubs + register IT/financial
candidates) produced a ranked target list and a relationship graph:
- **11 ranked pitch targets**, **117 source-cited relationship edges**.
- High amenability: **TPG/iiNet** (280k-customer breach Aug 2025), **Iress**
  (OneVue GitHub-credential breach May 2024), **Woolworths** (MyDeal 2.2M-customer
  breach), **Uber AU** (1.2M-Australian breach + OAIC determination).
- Medium: MYOB, Pepperstone (vendor-credential breach), Quantium, Costa
  (phishing breach), Endeavour (credential-stuffing). Low: Macquarie Data
  Centres, Nick Scali.

Saved → `corpus-crawled/cyber-insurance-network-2026-06-18.json` (+ folder README).

### 3. Remote NER + OpenIE extraction
The 11 crawl targets were extracted **remotely on the cloud vLLM**
(Qwen2.5-3B-Instruct), not local Ollama:
- **292 entities, 355 triples** across 11 files in `corpus-tuples-crawled/`.
- Each file carries source provenance + amenability.

## Methodology & findings
- **Web crawl + adversarial verification.** Every relationship/incident carries a
  source URL; caveats retained rather than asserted (e.g. Uber's "Australian-HQ"
  flagged false; PwC not confirmed as Uber's statutory auditor).
- **Chunking required for dense passages.** 6 of 11 relationship-dense passages
  overflowed the OpenIE 4096-token generation cap on a single passage (→ 0
  triples). Re-extracting with ~3 findings per passage recovered all of them.
  Lesson for the ingestion path: crawl-synthesized (relationship-dense) text must
  be **chunked before extraction**, unlike the naturally short register rows.

## Artifacts
- `corpus-crawled/` — raw crawl reports (ranked targets + relationship graph + sources).
- `corpus-tuples-crawled/` — NER+OpenIE tuples extracted from the crawl findings
  (event/intelligence layer), each with provenance.
- `notes/retrieval-mcp.org`, `notes/local-gfm.org`, `notes/mcp.org` — MCP /
  serving / distribution plans. `.mcp.json` — working Windows→WSL launch form +
  correct dataset label (`union-0-5-canon-eq`).

## NOT YET DONE — recompilation into the final foundation model
Today's crawled tuples are **not yet incorporated into the deployed G-Reasoner
foundation model**. The following recompilation steps remain:
1. **Fact-gate** the crawled tuples (verify entities/ABNs; web-derived edges have
   no register ground truth — keep provenance + confidence).
2. **Entity-resolution / canonicalisation** onto the register backbone (ABN
   primary key) so crawled entities merge with existing register nodes rather
   than duplicating.
3. **Merge** the new edges into the union graph (event/intelligence layer fused
   onto the structural register layer).
4. **Stage-2 rebuild** (re-embed the expanded graph with the checkpoint's pinned
   embedder) and **GFM / G-Reasoner re-index**, then redeploy.

Until those are done, the live service (`union-0-5-canon-eq`) does **not** reflect
today's crawled intelligence — the tuples sit in `corpus-tuples-crawled/` awaiting
the recompile.
