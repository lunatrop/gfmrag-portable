# Fact Gating for Unstructured Prose

How to verify LLM tuple-extraction when the corpus is **unstructured prose**
(news articles, commentary) and there is **no structured answer key**.

Companion to [FACT GATING FOR STRUCTURED DATA.md](FACT%20GATING%20FOR%20STRUCTURED%20DATA.md),
which covers the register corpus where ground truth is free. This doc is the
plan for the roadmap's crawled-news layer (see [pipeline.org](pipeline.org),
Stage 5 usage workflow + genre-risk notes).

---

## Why the structured gate doesn't transfer

The structured gate measured **recall against a free, exact answer key**: every
passage came from a CSV row, so "did extraction preserve the known facts" was
counted directly.

Prose has no answer key. The verification question splits into two that the CSV
let us conflate — and they must be attacked separately:

| Question | Authority | Checkable? |
|---|---|---|
| **Faithfulness to source** — does the triple follow from what the article *says*? | the article text itself | YES — local and gradable |
| **Truth in the world** — is what the article says actually *true*? | reality / other sources | only via corroboration |

So the pivot is: measure **faithfulness (precision)** rigorously per-triple, and
**approximate truth** through cross-source corroboration. Recall stops being a
per-document gate and becomes a *sampled* benchmark.

---

## Layer 1 — Faithfulness (the extraction gate)

### Provenance is the foundation
Change the OpenIE step to emit, **per triple, the source sentence + char
offset** it was extracted from. This converts the unanswerable "is this triple
real?" into the local, checkable "does span *X* support triple *T*?" Nothing
below works without it. It is a prompt/schema change to extraction.

### Span-entailment check (the workhorse), two tiers
- **Cheap / deterministic — quote-anchoring:** require the entity and object to
  appear as verbatim (normalised) substrings of the cited span. High precision,
  misses paraphrase and inference. This is the prose analogue of the structured
  gate's substring floor.
- **Expensive / semantic — LLM-judge or NLI:** "does this sentence support this
  claim? default to NOT-supported if uncertain." Adversarially framed. Catches
  paraphrase; costs tokens; **must be calibrated** (see below).

### Round-trip back-verification
Render the triple back to a sentence, ask the judge "is this stated in the
passage?" An independent second vote on the same span.

### This is what kills wrong-binding
The documented genre-risk failure — KPMG events bound to Arthur Andersen's 2002
collapse — is a faithfulness failure the structured gate *could never catch*.
Provenance + entailment does: `[KPMG, did X, 2002]` is not entailed by a span
that actually says Arthur Andersen did X. The triple fails the gate at its own
cited source.

---

## Layer 2 — Truth in the world (the harder layer)

### Cross-source corroboration
Build the graph across many articles; score each edge by how many **independent**
sources assert it. One source = "unverified"; three = trustworthy. Contradictions
between sources are flagged, not silently merged.

### Anchor to the structured backbone — highest-value move for this project
We already own a ground-truth graph: the register. News tuples link to register
entities via entity-linking, so a news claim about a register company is
**partially hard-gateable**:

- **Identity facts** (the entity exists, its ABN) — hard-gated by exact match
  against the register + company registries + Wikidata. Same `WOOLWORTHHS`-class
  reverse check as the structured gate, now against external KBs.
- **Event/relationship facts** (a breach, a subcontract) — soft-gated by
  provenance + entailment + corroboration; cannot be hard-verified.

This **mixed gating** — identity hard, events soft — is the realistic model for
the supply-chain/lead-gen use case.

---

## What carries over, what changes

| Aspect | Structured | Prose |
|---|---|---|
| Recall | per-doc gate (free) | **sampled** benchmark on a hand-labelled golden set |
| Faithfulness | implicit | the **primary, per-triple** gate (provenance + entailment) |
| Suspect entities | matches no register row | resolves to no entity in **any** trusted KB |
| Relation sprawl | mild | worse (unbounded phrasings) → add canonicalisation/clustering |
| Wrong-binding | invisible | caught by span-entailment |

### Calibrate the judge — never trust it blind
The LLM-judge is itself a model that can be wrong. Hand-label a small golden set
(~50 articles, annotated triples) to (a) estimate recall and (b) **measure the
judge's own precision/recall against humans**. Use a *different / stronger* model
as judge than as extractor, so they don't share blind spots. A judge whose
agreement with humans you haven't measured is not a gate.

---

## The release rule (where it actually matters)

`pipeline.org` states the stakes: asserting a false breach about a real company
is **defamation risk**, not a quality bug. So a news-derived claim reaching a
prospect must satisfy **all three**:

1. entity exact-matches a real registry entity (hard, deterministic),
2. the triple is span-grounded **and** judge-verified as entailed by its source,
3. ideally corroborated by ≥2 independent sources.

Anything failing (2) or (3) is retained as **"unverified — single source,"**
surfaced internally, **never asserted** outward.

---

## Architecture (cheap floor first)

1. **Deterministic floor** — quote-anchoring + entity-resolves-to-KB. Rejects
   the obvious; free.
2. **Judge layer** — span-entailment, run only on what the floor can't clear.
   Calibrated against the golden set.
3. **Graph layer** — cross-source corroboration scoring; contradiction flags.
4. **Golden set** — periodic recall estimate + judge calibration.

Same philosophy as the structured gate — a cheap deterministic floor with
expensive semantic checks layered only where they earn their cost. The
difference: for prose the floor clears far less, so the judge layer does the
heavy lifting and **must itself be measured**. The structured register gate was
the dress rehearsal precisely because, there, every claim was gradable — proving
the discipline before extending to text that isn't.
