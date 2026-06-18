# corpus-crawled

Raw **web-crawl results** — the intelligence-gathering output, before tuple
extraction. Each file is a synthesized crawl report: ranked targets, a
source-cited relationship graph, and caveats.

Distinct from:
- `corpus-tuples-crawled/` — the NER + OpenIE **tuples extracted from** these
  crawl findings (graph-ready entities/edges).
- `corpus-tuples/` — register-derived (structural) tuples.

Every relationship and incident carries a source URL; adversarial caveats are
retained in the report (e.g. unconfirmed auditors, mis-stated HQ) rather than
asserted as fact.

## Entries
- `cyber-insurance-network-2026-06-18.json` — 14-company crawl over the session's
  company network. Ranks Australian companies by cyber-insurance pitch
  amenability (driven by breach history, data-sensitivity sector, size,
  supply-chain exposure) and assembles the supplier/owner/auditor/competitor
  relationship graph. High targets: TPG/iiNet, Iress, Woolworths, Uber AU.
