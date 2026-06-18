# Network analysis — cyber-insurance crawl (2026-06-18)

Structural findings from surveying the day's crawl and extractions. All facts
trace to the artifacts referenced at the bottom; quantitative claims come from
analysing the 117 relationship edges and 11 target profiles in the crawl report.

## Source artifacts
- **Crawl report (raw intelligence):**
  [`corpus-crawled/cyber-insurance-network-2026-06-18.json`](../corpus-crawled/cyber-insurance-network-2026-06-18.json)
  — 11 ranked pitch targets, 117 source-cited relationship edges.
- **Tuple extractions (NER + OpenIE, remote vLLM):**
  [`corpus-tuples-crawled/`](../corpus-tuples-crawled/) — 12 files
  (`crawl-*.json` + `rasier-pacific-uber.json`), 292 entities / 355 triples.
- **Day report:** [`README/CRAWL-AND-EXTRACTION-2026-06-18.md`](../README/CRAWL-AND-EXTRACTION-2026-06-18.md).
- Register backbone (structural layer): `corpus/`, `corpus-tuples/`.

## Findings

### 1. The Big-4 auditors are the hidden connective tissue
Every target is audited by one of four firms, and each firm silently bridges
otherwise-unrelated companies:
- **PwC** → Uber, Macquarie Data Centres, Altium, Envato (Uber link is
  parent/advisory, *not* a confirmed statutory engagement — flagged in the crawl).
- **Deloitte** → Woolworths, Endeavour, Quantium (one corporate family).
- **KPMG** → TPG, Costa, Nick Scali.
- **EY** → Iress, Nick Scali.

In a supply-chain-risk graph the auditor is a hub you'd otherwise never see: a
single audit-firm incident propagates across its whole client base. (cf. the KPMG
turmoil extracted earlier in the session.)

### 2. Quantium is a systemic-contagion node — with no breach of its own
Woolworths owns ~80% of Quantium, yet it holds **CBA banking data** (CommBank iQ),
**Telstra** data, Woolworths loyalty data, **Walmart/ASDA**, *and* powers
**Iress's FundsFlow (~A$130bn wealth data)**. One analytics firm sits atop
grocery + banking + telco + wealth data at once — its risk is *inherited and
aggregated*, not from any incident. This is the literal "systemic blast radius"
the G-Reasoner blueprint predicted.

### 3. Woolworths is the densest node (13 edges)
Owns Quantium, spun off Endeavour, owns the breached MyDeal, plus
Petstock/PFD/PetCulture; supplied by Costa; delivered by Uber Eats → DoorDash.
Hub degree (top nodes): Woolworths 13, MYOB 11, Nick Scali 11, TPG 10, Datacom
10, Envato 10, Quantium 9, Costa 8, Iress 7, Altium 7.

### 4. Stolen credentials dominate the attack surface
Across the breaches found, credential compromise recurs (≈5 incidents), and the
*third-party* variant is the pattern: Pepperstone (vendor credential → CRM),
Iress (stolen GitHub credential → OneVue), Uber (contractor / Lapsus$), TPG/iiNet
(employee credentials), Woolworths MyDeal (compromised credential) — plus the
VIQ→e24 offshore-subcontractor case from the earlier crawl. The data writes the
cyber-insurance pitch: the network's #1 risk is supply-chain credential
compromise. (Signal tally: credential 5, ransom 4, employee 3, phishing 3,
third-party 2, contractor/github/lapsus/credential-stuffing 1 each.)

### 5. The hyperscalers are shared single points of failure
AWS underpins Datacom, Envato, Macquarie Data Centres; Microsoft underpins
Datacom, MYOB, Macquarie; Google Cloud underpins Quantium + Macquarie. A
cloud-provider outage cascades across unrelated targets.

### 6. "Australian" is a thin label on most targets
Largely foreign/PE-controlled: Uber (US/Netherlands), MYOB (KKR), Altium
(Renesas/Japan), Envato (Shutterstock/US), Pepperstone (~60% Lock's FX), Costa
(Paine Schwartz/US PE + Driscoll's), Datacom (44% NZ Super Fund). The register
entity is Australian; the control usually isn't.

### 7. The random lowest-band pick was a global giant
RASIER PACIFIC — drawn at random from the *smallest* revenue band (0–99M) — is
Uber. Register revenue bands describe the filing SPV, not the group behind it.

## Targeting takeaways
- **Strongest single prospect: TPG/iiNet** — freshest (Aug 2025) and largest
  (~280k customers) breach, high-data-sensitivity telco sector.
- **The paradox: Macquarie Data Centres** — biggest blast radius (secure gateway
  for ~42% of the federal government + the ATO) yet ranked *Low* amenability,
  because it is itself a cyber provider that likely self-insures. Highest risk ≠
  best customer.

## Caveat
These edges/incidents are web-crawl-derived and source-cited but **not yet
fact-gated, entity-linked, or merged into the foundation model** (see the day
report's "recompilation" section). Treat as analyst intelligence pending the
graph recompile.
