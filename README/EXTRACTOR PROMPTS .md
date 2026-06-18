# Extractor prompt profiles — per-dataset NER/OpenIE prompts

Extraction prompts are corpus-dependent, so they are **data, not code**: a
`prompts.yaml` placed in a dataset's `raw/` directory (beside
`documents.json`) overrides the packaged defaults for that dataset only.
Implemented in shared library code, so it applies identically to **local
(Ollama) and cloud (vLLM) extraction** — same `KGConstructor`, same
`LLMOPENIEModel`, no backend switches.

## Resolution order

1. `<data_root>/<data_name>/raw/prompts.yaml` — auto-applied by
   `KGConstructor` when present (highest priority)
2. `prompts_file` passed to `LLMOPENIEModel` (hydra-overridable:
   `openie_model.prompts_file=...`)
3. Packaged defaults (`openie_extraction_instructions.py`, HippoRAG-derived)

Key files:
- `gfmrag/graph_index_construction/prompt_profiles.py` — loader + schema doc
- `prompt-profiles/au-register.yaml` — the Australian Modern Slavery Register
  profile (identifier-aware: exact ABN extraction, ABN triples first, joint
  statements expanded pairwise both directions, attributes repeated per entity)

## Profile schema (prompts.yaml)

```yaml
ner_instruction: |        # system message for the NER call
openie_instruction: |     # system message for the OpenIE call
one_shot:
  passage: |              # example document, ideally from the target corpus
  entities: [ ... ]       # expected NER output (list of strings)
  triples:                # expected OpenIE output
    - [subject, relation, object]
```

The loader mirrors the packaged message structure exactly (system + one-shot
human/ai pair + templated user turn), so a profile changes *content*, not
*shape*.

## Using a profile

### Locally

```bash
# Place the profile beside the shard's documents.json:
cp prompt-profiles/au-register.yaml corpus-shards/shard-0/raw/prompts.yaml
# Then mint stage-1 as usual (LOCAL SETUP.md §2) — KGConstructor logs
# "Loaded prompt profile from ..." when it picks the file up.
```

### Cloud

Copy the profile into each shard directory in the data bucket so it sits
beside `documents.json` when the extractor mounts it:

```bash
gsutil cp prompt-profiles/au-register.yaml \
  gs://tautsec-graph-crawler-gfmrag-data/shard-K/raw/prompts.yaml
```

## Caveats (read before re-minting)

1. **The profile is per-shard-directory and must be physically present** —
   nothing distributes it automatically. When cutting new shards, copy it into
   every `raw/` dir you intend to extract (a sensible future addition to the
   shard-maker scripts).
2. **Local OpenIE cache does NOT invalidate on profile changes.** The results
   cache (`tmp/kg_construction/<fingerprint>/`) fingerprints the constructor
   config; the runtime-applied `raw/prompts.yaml` is not part of it. After
   editing a profile, clear `tmp/kg_construction/` (or set `force=true`) or a
   re-mint will silently reuse extractions made with the old prompts. Cloud
   pods get fresh ephemeral tmp each run, so this is a **local-only** trap.
3. **Scope: extraction only.** The profile covers passage NER + OpenIE inside
   `LLMOPENIEModel`. Query-time NER (`LLMNERModel`, used by the retriever) is
   a separate class with its own prompts — including the frozen-by-test
   single-turn prompt for local Ollama models — and is deliberately not
   affected.
4. **Small models are prompt-fragile.** Instruction changes that are neutral
   on a 7B can collapse a 3B (measured: three reasonable NER rewordings each
   drove qwen2.5:3b to permanent empty output). After any profile edit,
   re-mint shard-0 locally (16 docs, ~30 min, free) and check entity/triple
   counts before spending cloud money at scale.

## Why the au-register profile exists

Measured 3B weaknesses on this corpus (see `corpus-tuples/ladder-results.md`
and `pipeline.org`): ABN recall 41–56% (joint statements shed parenthetical
ABNs) and fragmented relation phrases. The profile orders ABN triples first so
output-length truncation drops repeated attributes rather than identifiers,
and demands exact-as-written identifier extraction — feeding the downstream
fact-verification gate (every ABN in marketing output must exact-match the
register).
