# Fact Gating for Structured Data

How the gfmrag pipeline verifies that LLM tuple-extraction preserved the truth,
when the corpus was generated from a structured source.

Implementation: [`scripts/verify_tuples.py`](scripts/verify_tuples.py).
Companion docs: [pipeline.org](pipeline.org) (where the gate sits in the
pipeline), [corpus-tuples/ladder-results.md](corpus-tuples/ladder-results.md)
(the numbers it produced).

---

## The core idea

LLM extraction (NER + OpenIE) is non-deterministic and lossy — it drops facts,
fragments relations, and occasionally invents things. Normally you can't *score*
that without hand-labelled ground truth.

But this corpus is **rendered from a structured source** (the Australian Modern
Slavery Register CSV). Every passage was generated from one CSV row whose fields
are known exactly. So ground truth is **free**: re-read the row, and check
whether each known fact survived into the extracted tuples.

That makes fact gating a **recall** measurement first and foremost:

> *Of the facts we know are true for this document, how many made it into the
> knowledge graph?*

plus a lighter **precision-flavoured** reverse check for invented entities.

## Why this is the right gate (and a dress rehearsal)

- **Objective, not a judgement call.** "ABN recall went 45% → 62%" was *counted*,
  which is what let the 3B-vs-7B and generic-vs-profile comparisons settle
  cleanly instead of by eyeballing samples.
- **Zero labelling cost.** The structured source *is* the answer key.
- **It's practice for the layer that has no answer key.** The roadmap adds a
  crawled-news layer where ground truth does *not* exist. Getting the
  verification discipline right on the register — where every claim is gradable
  — is what earns trust before extending to text you cannot score.

---

## How a run works

```
python scripts/verify_tuples.py \
    --shard corpus-tuples/shard-N \
    --documents corpus-shards/shard-N/raw/documents.json
    # --register defaults to corpus/all-statements_2026-04-18.csv
```

1. **Load ground truth.** Read the register CSV into a dict keyed by statement
   `IDX`.
2. **Match docs to rows.** Each document title is
   `Modern slavery statement <IDX>: <NAME>`; parse `IDX`, look up its row.
3. **Build a search "haystack" from the tuples.** Concatenate every normalised
   `nodes.csv` name and every normalised `source relation target` edge string
   into one blob per the shard. Facts are checked for *presence* anywhere in it
   (node OR edge), because a preserved fact is a pass regardless of which
   structure it landed in.
4. **Normalise both sides identically.** Lowercase, punctuation → spaces,
   collapse whitespace — mirroring the extractor's `processing_phrases`, so
   `ABN 96 060 703 120`, `96 060 703 120`, and `96060703120` compare fairly.
5. **Per-fact-class presence check**, per document:
   | Class | Source field | Note |
   |---|---|---|
   | entity names | `ReportingEntities` | ABN parentheticals stripped |
   | ABNs | `ABN` | 11-digit; tried spaced *and* unspaced |
   | revenue band | `AnnualRevenue` | |
   | reporting period | `PeriodStart` + `PeriodEnd` | |
   | HQ country | `HeadquarteredCountries` | any listed country matches |
   | industry sector | `IndustrySectors` | first sector |

   Each hit increments `found`; **recall = found / expected** per class.
6. **Reverse check — "suspect entities".** Scan company-shaped nodes (matching
   `pty|ltd|limited|holdings|inc|plc|corporation`) that match **no** register
   entity. These are candidate hallucinations or LLM typos — the `WOOLWORTHHS`
   class (a real misspelling caught in the first smoke test). This is the one
   precision-side signal.
7. **Output.** Per-class recall table, overall percentage, and the suspect list:

   ```
   fact       found expected   recall
   entity       446      455      98%
   abn          301      732      41%
   revenue      256      256     100%
   period       253      256      99%
   hq           256      256     100%
   sector       248      256      97%
   OVERALL: 1760/2211 facts preserved (80%), 11 suspect entities
   ```

---

## What it catches (and what it does not)

**Catches well:**
- Dropped facts — the headline use. ABN recall is the standing weak spot it
  surfaced: the 3B model sheds parenthetical ABNs in entity-dense joint
  statements (56% on tiny shards → 41% at 256 docs), which directly motivated
  the `au-register` prompt profile (`has ABN`-first triples).
- Hallucinated entities — the suspect-node reverse check.
- Regressions — run it per shard/config; a quality drop shows up as a number.

**Does NOT catch (by design / known limits):**
- **Presence, not binding.** An ABN counts as found if it appears *anywhere* in
  the document's tuples, even if attached to the wrong entity. The gate scores
  "did the fact survive," not "is the triple semantically correct." Catching
  wrong-binding (e.g. an attribute bound to the wrong co-filer, or the
  auditor-style cross-entity hallucination documented under genre risk) needs a
  separate *structural* check.
- **Relation quality.** Relation fragmentation (e.g. `filed` / `filed with` /
  `filed by` / `filed a single…` as distinct relations — 72 relations for ~8
  semantic ones under generic prompts) is invisible to the gate; assess that by
  reading `relations.csv`.
- **Substring false positives.** Rare, since register field values are
  distinctive, but possible in principle.
- **Suspect-list artifacts.** `&`-joined multi-entity names sometimes flag as
  suspects when legitimate — treat suspect *counts* as a trend signal, eyeball
  the list before acting.

---

## Generalising to other structured corpora

The pattern transfers to any corpus rendered from structured records:

1. Keep a stable **doc-id ↔ source-row** key in the rendered passage (here, the
   register `IDX` in the title).
2. Enumerate the **fact classes** the source guarantees, and their fields.
3. Normalise extracted tuples and source values the *same* way the extractor
   normalises text.
4. Score **recall** per class (did known facts survive) + a **reverse check**
   for entities/values present in the graph but absent from the source
   (candidate hallucinations).
5. Decide a **release rule**: e.g. "no lead-gen output unless the entity and its
   ABN both exact-match a register row" — recall alone is necessary, not
   sufficient; the binding check is the gate for outward-facing claims.

The gate is the cheap, deterministic floor. The expensive structural/semantic
checks layer on top only where the cheap floor proves they're needed.
