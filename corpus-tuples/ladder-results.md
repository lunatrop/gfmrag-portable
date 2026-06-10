# Cost-measurement ladder — results

Shards: `corpus-shards/` (seed 42, disjoint; 16/64/256/1024/4096/11634 = 17,090 docs).
Success criterion per rung: every doc yields non-empty entities AND triples; cost
and sec/doc recorded for extrapolation.

| Rung | Docs | Backend | Wall | sec/doc | Entities | Triples | Malformed | Cost |
|---|---|---|---|---|---|---|---|---|
| 0 | 16 | local qwen2.5:3b | 23.3 min | 87 (52–139) | 132 | 140 | 15 (11%) | A$0 |
| 1 | 64 | vLLM 7B (GCP) | | | | | | |
| 2 | 256 | vLLM 7B (GCP) | | | | | | |
| 3 | 1,024 | vLLM 7B (GCP) | | | | | | |
| 4 | 4,096 | vLLM 7B (GCP) | | | | | | |
| 5 | 11,634 | vLLM 7B (GCP) | | | | | | |

## Rung 0 notes (2026-06-10)

- 16/16 docs succeeded (`shard-0-local.json`). Avg 8.25 entities / 8.75 triples per doc.
- Malformed = wrong arity (2- or 4-element "triples", or empty object slot), not
  garbage — content is present but misshapen. This is exactly what vLLM's guided
  JSON decoding (`--guided-decoding-backend outlines`) is expected to eliminate
  at rung 1+; compare this 11% rate against the cloud rungs.
- Clean triples are high quality: ABN links, HQ, sectors, revenue bands, and
  included-entity (subsidiary) relations all extracted correctly.
- Input wart FIXED post-rung-0: entities without an ABN gained a stray `)` from
  the converter's parser (e.g. `GME PTY LTD.)`). `parse_entities` now only
  restores the paren the splitter consumed when one is actually dangling;
  shards regenerated (same seed/membership — only affected passages changed,
  709 → 244 `X.)` occurrences, the remainder being genuine names like
  `FUJITSU GENERAL (AUST.) PTY LIMITED`). Rung 0 was measured on the pre-fix
  shard-0 (1 of 16 docs affected) — not re-run; rung 1+ use the clean shards.
  Known residual: an ABN-less entity followed by a comma can't be split from
  the next entity (splitter keys on `),`; names may contain commas).
