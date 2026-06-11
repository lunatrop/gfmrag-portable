# Extraction Campaigns

How to run a **multi-shard extraction campaign** (e.g. the remaining shard-4 +
shard-5, ~92% of the corpus, or any future corpus) efficiently — minimising the
per-shard cold overhead that dominates small runs.

Companion: [CLOUD RUN SETUP.md](CLOUD%20RUN%20SETUP.md) (runbook),
[corpus-tuples/ladder-results.md](corpus-tuples/ladder-results.md) (timings),
[notes/NLP-sequence.org](notes/NLP-sequence.org) (where the time goes).

---

## The overhead reality

`gfmrag-extract` is a Cloud Run **Job**. Jobs **tear down on completion** — there
is no warm-instance reuse between executions. Every run re-pays its fixed
startup. So a campaign's economics are governed by how much of that startup is
persisted vs re-paid, and by how well it's amortised over documents.

### What is persisted (paid once, ever)
- **Model weights** — GCS HF cache (`…-hf-cache` bucket). No re-download.
- **vLLM image** — Artifact Registry Docker Hub proxy. No Docker Hub re-pull.
- **ColBERT CUDA extensions** — baked into the extractor image at build time
  (`bake_extensions.py`); no ~84s JIT compile per run.
- **All of the above survive `terraform destroy`** of the compute stack (they
  live in the `persistent/` stack).

### What is re-paid on every job execution (Jobs can't stay warm)
- **Image load** (~slimmed CUDA-runtime base + venv) onto a fresh instance.
- **Python imports** (torch/faiss, minutes) — fresh process each time.

### What a warm window buys (Services only)
vLLM is a **Service**, so it stays warm for a few minutes after the last request
(idle window, ~minutes, not guaranteed). Starting the next shard promptly lets
its OpenIE calls hit a warm vLLM and skip the ~167s cold start.

---

## The three levers (most to least impactful)

1. **Bigger shards.** Pack each task as large as the 1-hour GPU task cap allows
   — **~768 docs proven** to finish attempt-1 with margin (checkpointing makes
   an over-cap shard resume rather than fail). This amortises the unavoidable
   per-job startup over the most documents. Single biggest lever.

2. **Pin vLLM warm for the campaign.** Set vLLM `min_instances=1` for the
   duration so it never cold-starts across *any* shard (~A$1/hr). For a
   back-to-back multi-shard run this is cheaper than re-paying ~167s cold starts
   and removes the idle-window gamble. Flip back to 0 when done.

3. **Warm-up the dependency before each batch.** `scripts/warm_qa.sh` (for QA)
   and a `/health` ping (for vLLM) absorb cold starts deliberately, with status
   messages, so timed runs measure inference not setup.

> A warm **extractor Service** (instead of a Job, `min_instances=1`) would
> persist *everything* including imports — the only way to avoid re-paying the
> ~5-min import cost per shard. Worth it only for a large sustained campaign;
> for a handful of big shards, bigger-shards + warm-vLLM is simpler.

---

## Campaign recipe

```bash
cd deploy/cloudrun

# 1. (optional, for many shards) pin vLLM warm for the run
#    edit terraform.tfvars: vllm_max_instances stays 2; to force-warm, the
#    simplest is to keep one instance alive by periodic pings, or set a
#    min-instance on the service. Then:
terraform apply -auto-approve -var qa_enabled=true

# 2. shard the corpus into balanced ~512-768-doc shards (NOT the exponential
#    ladder — that was for cost measurement):
python scripts/prepare_corpus_shards.py --mode equal --shards 24 --out corpus-shards-prod
#    stage the au-register profile into each shard's raw/ (prompts.yaml)

# 3. upload + extract, one task per shard, in parallel up to the L4 allocation:
#    extractor_datasets = ["prod-0","prod-1",...]   (length = parallel tasks)
#    Mind the 3-GPU cap: parallel tasks + vLLM instances must total <= 3
#    (raise via the GPU quota request to widen this — g.co/cloudrun/gpu-quota).

# 4. each shard: fact-gate (scripts/verify_tuples.py) before trusting output.

# 5. copy tuples back to corpus-tuples/ BEFORE any teardown.
```

### Sizing & cost (from the ladder)
- Production rate ~**900–950 docs/hour/task** under full config (3B + profile +
  vLLM fan-out + baked image).
- Full 17k corpus ≈ **~19 task-hours**; at the current 3-GPU cap (1 task task +
  2 vLLM) ≈ ~19h wall, **~A$80–100**. A quota bump to 6–8 L4s roughly halves
  wall-clock by running more tasks in parallel.

### Guard-rails
- **1-hour GPU task cap** — shards must extract in <1h; checkpointing
  (`openie_checkpoint.jsonl`, synced to the bucket) makes a retry *resume*, but
  keep shards comfortably under the cap.
- **ID-token lifetime 1h** — the extractor's vLLM auth token; same bound.
- **3-GPU regional allocation** — parallel extractor tasks + warm vLLM instances
  share it; size `extractor_datasets` accordingly until quota is raised.
