# Cost-measurement ladder — results

Shards: `corpus-shards/` (seed 42, disjoint; 16/64/256/1024/4096/11634 = 17,090 docs).
Success criterion per rung: every doc yields non-empty entities AND triples; cost
and sec/doc recorded for extrapolation.

| Rung | Docs | Backend | Wall | sec/doc | Fact gate | Suspects | Cost (est) |
|---|---|---|---|---|---|---|---|
| 0 | 16 | local qwen2.5:3b | 23.3 min | 87 (52–139) | — (pre-gate) | — | A$0 |
| 0c | 16 | vLLM 3B (GCP) | ~21 min | 79 | 90% (ABN 56%) | 0 | ~A$1.5 |
| 1 | 64 | vLLM 3B (GCP) | 21.0 min | 19.7 | 81% (ABN ~45%) | 0 | ~A$1.6 |
| 2 | 256 | vLLM 3B (GCP) | 21.8 min | 5.1 | 80% (ABN 41%) | 11 | ~A$1.7 |
| 2-7b | 256 | vLLM 7B (GCP) | 41.3 min* | 9.7 | 76% (ABN 34%) | 4 | ~A$3.1 |
| 2-p2 | 256 | vLLM 3B + au-register profile | 24.6 min | 5.8 | *86% (ABN 62%)* | 6 | ~A$2.0 |
| 3 | 1,024 | vLLM 3B (GCP) | DNF (>1h cap) | — | — | — | ~A$2 |
| 3-p2 | 1,024 | 3B + profile + checkpoint | 67.7 min (1 retry, resumed) | 4.0 | 85% (ABN 60%) | 26 | ~A$7 |
| 4 | 4,096 | vLLM (GCP) | | | | | |
| 5 | 11,634 | vLLM (GCP) | | | | | |

## Cloud rungs 0c–2 notes (2026-06-10/11)

- *The curve is flat*: 16, 64 and 256 docs all take ~21–22 min. Fixed overhead
  (image pull + imports + CUDA JIT + ColBERT index ≈ 15 min) dominates; warm
  vLLM with continuous batching makes marginal extraction ≈ 0.2–0.5 s/doc.
- *Extrapolation — FALSIFIED at rung 3*: the flat-curve projection (~25–30
  min for 1,024 docs) was wrong. Attempt 1 of rung 3 was still running at the
  1h task cap and was killed; Cloud Run then retried FROM SCRATCH (OpenIE
  intermediates are container-local tmp — retries inherit nothing) with a
  30-min wait between attempts, so the execution could only loop to failure.
  Cancelled after retry 1 (execution gfmrag-extract-4vvnn). Scaling between
  rung 2 and 3 is superlinear — suspects: synonym-edge/EL phase over ~4×
  the phrases, PLAID index build, and vLLM throughput saturation at fixed
  concurrency. Decomposition needs per-phase timestamps from logs.
- *Revised production rule*: equal shards of ≤ ~256–500 docs per task (256
  is proven at 21.8 min; 512 untested), run in parallel. Full 17k corpus ≈
  34–68 parallel-or-queued tasks; with 2 concurrent task GPUs ≈ 6–12h
  wall-clock, cost still O(A$50–120) — higher than the flat-curve estimate;
  re-measure after a 512-doc probe before committing.
- *Resumability gap (the structural fix)*: pointing the constructor tmp dir
  at the GCS mount would make OpenIE results survive retries, BUT per-line
  appends through gcsfuse are pathologically slow (the 1MB/s lesson). Proper
  fix = periodic checkpoint sync of openie_results.jsonl to GCS; until then,
  keep tasks comfortably under the cap.

## Rung 3 completion + Tier-2 closure (2026-06-11, execution 67rbt)

- *Checkpoint-resume validated in production*: attempt 1 killed at the 1h cap
  with ~95% of OpenIE done; the retry restored the checkpoint instantly and
  finished extraction + EL + graph in ~7 min. Total 67.7 min wall — the
  failure mode that DNF'd rung 3 is retired.
- *Sizing datum (replaces the 512 probe)*: ~900–950 docs/hour/task under full
  production config (3B + au-register profile + 6000 triple-token cap + vLLM
  2-instance fan-out). Production shards: ~768 docs fits attempt 1 with
  margin; larger shards degrade gracefully via resume.
- *Quality holds at 4× scale*: 85% overall (vs 86% at 256), ABN 60% (vs 62%),
  revenue/period/HQ 100%, sectors 99%, suspect rate flat (~2.5%). Entity
  recall 87% — the 6000-token cap didn't fully cure the mega-joint dip;
  remaining entity misses concentrate in the largest joint statements
  (next lever: chunk or special-case statements with >6 co-filers).
- *Full-corpus projection (17k docs)*: ~18-19 task-hours → with 2 parallel
  task GPUs impossible under the 3-GPU allocation while vLLM fans out; at
  1 task + 2 vLLM ≈ ~19h wall, ~A$80-100. A quota bump to 6-8 L4s halves it.
- *Cost is overhead-dominated too*: ~A$1.5–1.7/rung regardless of size so far
  (task ≈ A$0.75 + vLLM active ≈ A$0.85). Full 17k corpus as 3–4 parallel
  equal shards projects ≈ *A$8–12 total* — consistent with the original
  A$10–20 estimate.
- *Quality at scale*: entities 98%, revenue 100%, HQ 100%, periods 99%,
  sectors 97% at rung 2. Overall drag is *ABN recall (56%→41%)* — joint
  statements shed parenthetical ABNs; the 3B-vs-7B A/B targets exactly this.
  First 11 suspect entities at rung 2 (some are gate-parser artifacts:
  &-joined ABN-less names) — eyeball before lead-gen use.
- vLLM cold start post-HF-cache: *3m03s* measured (was ~4.5 min downloading).
- Arity rate not yet instrumented cloud-side (guided decoding claim untested);
  fact-gate recall is the operative quality metric for cloud rungs.

## 3B-vs-7B A/B verdict (rung 2, identical 256 docs, 2026-06-11)

*3B wins outright* — better on recall AND cheaper, so the decision rule
("cheapest model whose verified-fact rate matches the best") isn't even
close: entities 98%→90%, ABN 41%→34%, overall 80%→76%, at ~2× the time and
cost (*7B wall includes one vLLM cold start — warm-up was skipped by an IAM
propagation race; even subtracting ~5 min the 2× gap stands). The 7B's one
win is precision (4 vs 11 suspect entities). The local single-passage
benchmark that favoured 7B did NOT transfer to corpus-scale fact recall.
=model_id= stays *Qwen2.5-3B-Instruct*; ABN recall in joint statements needs
a prompt/chunking fix, not a bigger model.

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
