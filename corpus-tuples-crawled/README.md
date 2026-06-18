# corpus-tuples-crawled

Web-crawl-derived NER + OpenIE tuples — the **event / intelligence layer**,
distinct from `corpus-tuples/` (register-derived structural layer).

Each file captures: the source passage, the **source URLs (provenance)**, the
raw extractor output (entities + triples, exactly as produced), and quality
notes. Web-derived edges have **no free register ground truth**, so provenance
+ a verification step are mandatory before these are admitted to the graph.

Pipeline position: these tuples entity-link onto the register backbone
(shared entities like Woolworths Group, Endeavour Group, Deliveroo, PwC, and
the Uber entities are already register nodes) and add relationship edge types
the register lacks (`partnered_with`, `competed_with`, `is_auditor_of`).

Before merge: (1) fact-gate / exact-match entity names against the register
(catches LLM typos), (2) attach provenance + confidence per edge, (3) dedup
bidirectional/duplicate triples.

## Entries
- `rasier-pacific-uber.json` — random lowest-band register entity (RASIER
  PACIFIC PTY LTD, an Uber AU subsidiary) → web crawl → verified connections to
  Woolworths (partner), Deliveroo (competitor), PwC (group auditor). Endeavour
  Group's Uber link was hypothesised and **refuted** (uses DoorDash/Menulog).
