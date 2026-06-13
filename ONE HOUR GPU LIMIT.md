# The 1-Hour GPU Limit on Cloud Run (and why we chose Cloud Run anyway)

A constraint that shapes the extraction architecture, and the cost rationale
that makes living with it the right trade — versus the GKE-style alternative.

Companions: [CAMPAIGNS.md](CAMPAIGNS.md) (how we work within the limit),
[deploy/cloudrun/README.md](deploy/cloudrun/README.md) (the Cloud Run stack),
`deploy/terraform/` (the parked GKE stack).

---

## The limit

A Cloud Run resource with a GPU attached has a **maximum request/task timeout of
3600 seconds (1 hour)**. We hit it empirically — the apply was rejected with
*"must be between 0 and 3600 seconds (1 hour) when using GPU"* — and again at
runtime, when a 1,024-doc extraction task was **killed at exactly 300s/then the
1h cap** mid-work. For contrast, a Cloud Run task **without** a GPU can run up to
24 hours; the 1-hour ceiling is GPU-only.

It applies to both shapes we use:
- **Jobs** (`gfmrag-extract`): a single task must finish extraction within 1h.
- **Services** (vLLM, QA): a single request must complete within 1h (we raised
  the QA request timeout to 900s for the lazy-init first query; the hard ceiling
  is still 3600s).

## Why Google imposes it

Not published in detail, but legible from the product design:
- **GPUs are a scarce, oversubscribed pool lent out serverlessly.** Cloud Run
  GPU's whole pitch — on-demand L4s, no reservation, billed per-second, granted
  without a quota request (no-zonal-redundancy tier) — only works if the
  scheduler can reclaim each GPU on a short horizon. A bounded task lease means
  every GPU returns to the pool within an hour.
- **No zonal redundancy ⇒ no migration promise.** In the cheap tier Google
  doesn't guarantee to carry you through a zonal capacity event; bounding task
  duration bounds the value of that (non-)commitment.
- **Jobs auto-retry**, so an unbounded GPU task with retries is an unbounded
  liability for both cost and fair scheduling.
- It's a **product-boundary signal**: serverless GPU is for inference and burst
  batch — work that decomposes into short units. Hours-long GPU holds are what
  GKE / Compute Engine / Cloud Batch are for.

## How we live with it

- **Shard size ≤ ~700 docs/task** (proven ~768 finishes with margin) so every
  task completes inside the hour. The full corpus runs as many balanced
  sub-shards, not one big job.
- **OpenIE checkpointing** (`openie_checkpoint.jsonl`, synced to the bucket
  every 25 docs): a task killed at the cap **resumes** on retry instead of
  restarting from zero — turning the cap from a hard failure into graceful
  degradation.
- **1h aligns with the ID-token lifetime** the extractor's vLLM auth uses, so
  one bound covers both.

## The alternative: a GKE-style rental, and why we didn't

The parked GKE stack (`deploy/terraform/`) runs the same workload on a managed
node pool. There is **no 1-hour task limit** there — a pod can hold a GPU for
hours or days, so a single long extraction "just works" and you'd never shard
for the cap or build checkpointing.

But that freedom is **rented by the hour, continuously**:

| | Cloud Run (chosen) | GKE node pool (alternative) |
|---|---|---|
| GPU billing | per-second, **only while a task/request runs** | per-hour, **for as long as the node exists** |
| 1-hour task cap | yes (work around with shards + checkpoint) | none |
| Idle cost | **≈ A$0** (scale-to-zero) | **~A$975/mo floor** for a kept-warm L4 node + cluster fee |
| GPU acquisition | on-demand, no quota request (NZR tier) | provision/reserve the node pool |
| Best for | bursty batch + scale-to-zero serving | sustained, long-running, queue-depth workloads |

## The cost-cutting rationale

Our extraction is **bursty**: a corpus arrives, we extract it over hours, then
nothing for days. On GKE you pay for the GPU node the **entire time it exists**,
idle or not — so an always-available L4 is a ~A$975/month floor whether or not
you're extracting. On Cloud Run you pay **only for the seconds a task actually
runs**, and idle cost is essentially zero (storage only).

For a workload that's busy a few hours and idle the rest, **per-second
scale-to-zero billing beats per-hour reserved capacity by a wide margin** — a
full-corpus extraction is single-digit-to-low-tens of AUD on Cloud Run, versus a
standing monthly node bill on GKE that you pay even on days you extract nothing.
The price of that saving is the 1-hour cap, which we neutralise cheaply with
shard-sizing + checkpointing. So the limit isn't an obstacle we tolerate — it's
the **direct consequence of the billing model we chose specifically to cut
idle cost**, and the engineering around it (small shards, resumable checkpoints)
costs far less than a month of idle GPU.

GKE remains the right call if the workload ever becomes **sustained** (continuous
high-velocity crawling/extraction 24/7), where a reserved node with committed-use
discounts would amortise and the per-second model would lose its edge. Until
then, Cloud Run + the 1-hour cap is the cheaper architecture.
