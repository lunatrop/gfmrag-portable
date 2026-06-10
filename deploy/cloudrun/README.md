# Deploy: gfmrag on Cloud Run (scale-to-zero variant)

Parallel draft of the GKE stack in `../terraform`, rebuilt on Cloud Run.
Same three workloads, near-zero idle cost, and IAM-authenticated endpoints
ready for **tautsec-benchmarking** to call.

**Apply one stack or the other, not both** — they define the same GCS bucket
and Artifact Registry names.

| Workload | GKE stack (`../terraform`) | This stack |
|---|---|---|
| vLLM (OpenAI API) | Deployment + internal LB + HPA on L4 node pool | `gfmrag-vllm` Cloud Run GPU service, `min_instances=0` |
| Extractor (batch NER+OpenIE) | Indexed Job on CPU pool, `JOB_COMPLETION_INDEX` | `gfmrag-extract` Cloud Run Job, `CLOUD_RUN_TASK_INDEX` |
| QA prompting (`/retrieve`, `/answer`) | GPU Deployment + LB + HPA (deferred) | `gfmrag-qa` Cloud Run GPU service (deferred, `qa_enabled`) |
| Idle cost | ~A$240/mo (GKE fee + lingering CPU node) | ~A$0 (storage only) |

Key differences:
- **No cluster, no node pools, no kubectl** — single Terraform provider, single apply.
- **Scale-to-zero is native** (`min_instance_count = 0`); no kubectl-scale dance.
- **Autoscaling on request concurrency**, not the CPU-HPA placeholder.
- **Cold start is the trade**: first request after idle pays image pull + model
  load (~1–3 min for vLLM; more for QA). Bake weights into the image or mount
  from GCS to cut it.
- **vLLM image** is pulled through an Artifact Registry *remote repo*
  (`dockerhub/`), because Cloud Run can't pull from Docker Hub.
- **Auth is IAM, not network**: no `allUsers`; each caller SA gets
  `roles/run.invoker` explicitly (TAUTSEC internal-calls rule).

## Deploy

```bash
cd deploy/cloudrun
cp terraform.tfvars.example terraform.tfvars   # already populated for tautsec-graph-crawler
export TF_VAR_hf_token=hf_xxx                   # only for gated models

terraform init && terraform apply

# Build + push the extractor image, stage corpus shards, then run a batch:
terraform output -raw image_push_command
gsutil -m cp -r ./data/shard-0 gs://$(terraform output -raw data_bucket)/shard-0   # etc.
terraform output -raw run_extraction_command

# Once the index is in GCS, enable the QA service:
terraform output -raw qa_image_push_command
terraform apply -var qa_enabled=true
```

## Calling from tautsec-benchmarking

Both services reject anonymous requests; callers present a Google **ID token**
for an SA holding `run.invoker`. Terraform creates a dedicated caller SA
(`gfmrag-benchmark-caller@...`) bound to the QA and vLLM services.

One-time setup:
```bash
gcloud iam service-accounts keys create gfmrag-caller-key.json \
  --iam-account $(terraform output -raw benchmark_caller_sa)
```
In Vercel project settings (tautsec-benchmarking), add:
- `GFMRAG_QA_URL` = `terraform output -raw qa_url`
- `GCP_SA_KEY` = contents of `gfmrag-caller-key.json`

Server-side route/helper (`lib/gfmrag.ts`):
```ts
import { GoogleAuth } from "google-auth-library";

const auth = new GoogleAuth({
  credentials: JSON.parse(process.env.GCP_SA_KEY!),
});

export async function gfmragAnswer(query: string, topK = 5) {
  const client = await auth.getIdTokenClient(process.env.GFMRAG_QA_URL!);
  const res = await client.request({
    url: `${process.env.GFMRAG_QA_URL}/answer`,
    method: "POST",
    data: { query, top_k: topK },
  });
  return res.data; // getIdTokenClient handles token mint + refresh
}
```
Call it only from API routes / server components — never the browser (the key
must stay server-side). Vercel↔GCP Workload Identity Federation can replace
the key later (keyless); the IAM bindings here don't change.

Expect the **first call after idle to take minutes** (cold start) — for nightly
benchmarking runs, fire a warm-up request first, or set `min_instances=1` for
the duration of the run.

## Known caveats (vs GKE)

- **Internal calls need ID tokens too.** On GKE the extractor hit vLLM over
  cluster DNS unauthenticated. Here every hop crosses Cloud Run IAM:
  - The extractor job fetches an ID token from the metadata server at task
    start and passes it as `OPENAI_API_KEY` (wired in `extractor_job.tf`).
    Tokens live 1h — shards that extract longer need a refresh hook in
    gfmrag's OpenAI client, or smaller shards.
  - The QA service (`deploy/serve/app.py`) mints and auto-refreshes ID tokens
    for `VLLM_AUDIENCE` via the metadata server (no-op off-GCP).
- **24h max per job task** — size corpus shards to finish within
  `extractor_task_timeout` (default 6h).
- **One GPU per instance** — fine for the 7B model; multi-GPU means GKE.
- Everything in the GKE README's "not production-hardened" list still applies
  where relevant (remote TF state, digest pinning, etc.).
