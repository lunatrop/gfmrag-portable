# Cloud Run Setup — gfmrag extraction & QA on GCP

Battle-tested runbook for deploying the gfmrag pipeline to Cloud Run and
passing the three-stage test: **(1)** deploy the infra, **(2)** extract tuples
from `corpus/` into `corpus-tuples/` with a Qwen vLLM, **(3)** query the
GFM-RAG 8M and 34M (G-Reasoner) checkpoints against the tuples.

Every checklist item below earned its place — the "gotchas" sections are
failures that actually happened on the first deployment (2026-06-10).

Companion docs: [deploy/cloudrun/README.md](deploy/cloudrun/README.md)
(stack reference), [big-cloud-downloads.org](big-cloud-downloads.org)
(what downloads when, and why).

---

## Phase 0 — Prerequisites

### Auth checklist (WSL — all gcloud work happens there, not Windows)

- [ ] `gcloud auth list` shows the right account active
- [ ] CLI credentials are *fresh*: `gcloud projects describe tautsec-graph-crawler`
      succeeds. If it says "Reauthentication failed":
      `gcloud auth login <account> --force`
      — **without `--force` gcloud silently re-uses the expired credentials.**
- [ ] Project set: `gcloud config set project tautsec-graph-crawler`
- [ ] **ADC is separate from CLI auth** and Terraform uses ADC:
      `gcloud auth application-default login`
      then `gcloud auth application-default set-quota-project tautsec-graph-crawler`
- [ ] Verify: `gcloud auth application-default print-access-token >/dev/null && echo ADC_OK`

### Billing & quota checklist

- [ ] Billing enabled on the project (`gcloud billing projects describe …`)
- [ ] Know your spend ceiling. Idle cost of this stack ≈ **A$0** (storage only);
      active GPU time ≈ A$1.2–1.6/hr per L4. A full shard-0 test run costs
      **single-digit AUD** including failed attempts.
- [ ] L4 GPU quota: Cloud Run L4s **without zonal redundancy** are granted
      on demand (no pre-request needed), but the *deploy-time* validator
      rejects `max_instances` above your regional allocation — see Phase 2
      gotchas.
- [ ] (Recommended) A budget alert exists on the billing account before
      scaling past the small rungs.

### Inputs checklist

- [ ] Corpus shards exist locally. Generate with:
      ```bash
      python scripts/prepare_corpus_shards.py --mode exponential --shards 6 --out corpus-shards
      # rungs: 16, 64, 256, 1024, 4096, rest   (cost-measurement ladder)
      # or --mode equal --shards 6 for balanced full-parallel shards
      ```
- [ ] Spot-check one passage per shard (`shard-N/raw/documents.json` is a
      `{title: passage}` dict — the format `kg_constructor` consumes).

---

## Phase 1 — Deploy the infrastructure

```bash
cd deploy/cloudrun
# terraform.tfvars is gitignored; copy from terraform.tfvars.example and set:
#   project_id, bucket_name, model_id, extractor_datasets, extra_invoker_members
terraform init
terraform apply        # ~21 resources; the extractor JOB will fail — expected, see below
```

### Settings that matter (terraform.tfvars)

| Setting | First-deployment value | Why |
|---|---|---|
| `model_id` | `Qwen/Qwen2.5-3B-Instruct` | ~6GB weights fit Cloud Run's 32GiB RAM-backed fs with headroom; 7B (~15GB) is the upgrade once proven |
| `vllm_max_instances` | `2` | Deploy-time validation rejects values above the regional L4 allocation |
| `extractor_datasets` | `["shard-0"]` | 16 docs — cheapest possible end-to-end proof |
| `extra_invoker_members` | `["user:you@example.com"]` | Without it, your own smoke tests get 401 — owner role does NOT bypass Cloud Run IAM |
| `qa_enabled` | `false` | Defer until the KG index exists in GCS |

### Phase 1 gotchas (all hit for real)

- [ ] **`max_instance_count` 400 error** → lower `vllm_max_instances` to fit
      the L4 allocation; raise later with a quota increase.
- [ ] **GPU job timeout 400 error** → GPU job tasks cap at **3600s**
      (conveniently equal to the ID-token lifetime). Size shards to finish
      inside an hour.
- [ ] **`gfmrag-extract` job fails to create: "Image not found"** → expected
      chicken-and-egg: the job validates its image at creation. Build the
      image (Phase 2), then `terraform apply` again.

---

## Phase 2 — Build the images (Cloud Build — no local Docker needed)

```bash
cd <repo root>
terraform -chdir=deploy/cloudrun output -raw image_push_command     # then run it
# ~20 min on E2_HIGHCPU_8. Context upload is ~280KB thanks to .gcloudignore.
```

### Image checklist — why the Dockerfile looks the way it does

- [ ] **`poetry.lock` is current**: if you touched `pyproject.toml`, run
      `poetry lock` first. *Stale lock = build fails at `poetry install`.*
- [ ] **CUDA devel base** (`nvidia/cuda:12.6.3-devel-ubuntu24.04`), not
      python-slim: ColBERT/pylate's PLAID indexer **JIT-compiles CUDA
      extensions at runtime** and needs `nvcc`, headers, `CUDA_HOME`, `ninja`.
      Pip's `nvidia-*` runtime libs are not enough — the job dies in
      `el_model.index` without the toolkit.
- [ ] **`VIRTUAL_ENV=/venv` env var is set**: with
      `POETRY_VIRTUALENVS_CREATE=false` and no `VIRTUAL_ENV`, poetry installs
      all 132 deps into the *system* python while the runtime runs
      `/venv/bin/python` → `ModuleNotFoundError: numpy` at job start.
- [ ] **Build-time import probe** (`RUN python -c "import numpy, torch, …"`)
      stays in the Dockerfile — it converts the entire env-mismatch failure
      class into a fast build failure instead of a GPU-job runtime crash.
- [ ] After ANY rebuild: **re-pin the job image** before executing — Cloud Run
      jobs resolve `:latest` to a digest at deploy time, not per execution:
      ```bash
      gcloud run jobs update gfmrag-extract --image <same :latest tag> --region us-central1
      ```

---

## Phase 3 — Extraction test (corpus → corpus-tuples)

```bash
# 1. Stage the input
gsutil -m cp -r corpus-shards/shard-0 gs://$(terraform -chdir=deploy/cloudrun output -raw data_bucket)/

# 2. (Optional but recommended) Warm vLLM first — avoids empty-NER results
#    from requests that land during its cold start:
TOK=$(gcloud auth print-identity-token)
curl -s -m 900 -H "Authorization: Bearer $TOK" "$(terraform -chdir=deploy/cloudrun output -raw vllm_url)/health"

# 3. Run it
gcloud run jobs execute gfmrag-extract --region us-central1 --wait

# 4. Verify + copy back (BEFORE any destroy — the bucket dies with the stack)
gsutil ls -r gs://<bucket>/shard-0/processed/stage1/        # nodes/edges/relations.csv
gsutil -m cp gs://<bucket>/shard-0/processed/stage1/*.csv corpus-tuples/shard-0/
```

### Pass criteria checklist

- [ ] Execution completes (`gcloud run jobs executions list --job gfmrag-extract`)
- [ ] `nodes.csv` contains **one `document` node per input doc** (16 for
      shard-0) — fewer means docs were clipped (usually vLLM cold-start
      errors; warm first, re-run)
- [ ] Edge density sane (shard-0 reference: **638 edges, 126 nodes,
      46 relations** ≈ 40 triples/doc)
- [ ] Spot-check triples against the register: entity names exact, ABNs
      labelled, joint statements linked both ways. (LLM-typo'd entity names —
      the `WOOLWORTHHS` lesson — are why downstream lead-gen needs an
      exact-match verification gate.)

### Timing expectations (so success doesn't look like a hang)

| Step | First run | Warm |
|---|---|---|
| vLLM cold start (image + 3B weights) | ~4.5 min measured | seconds–2 min |
| Extractor task image pull (~18GB) | ~10 min | fast (Cloud-Run cached) |
| OpenIE, 16 docs | ~2 min (warm vLLM) | — |
| EL: JIT compile + PLAID index | ~1–3 min | per-task (ephemeral cache) |

---

## Phase 4 — QA test (GFM-RAG 8M vs 34M G-Reasoner)

```bash
# 1. Build the serving image (same Dockerfile rules as Phase 2)
terraform -chdir=deploy/cloudrun output -raw qa_image_push_command   # run it

# 2. Verify the 34M checkpoint id exists on HF BEFORE planning the comparison
#    (8M = rmanluo/GFM-RAG-8M; confirm the exact G-Reasoner id on rmanluo's page)

# 3. Enable the service against the extracted shard
terraform apply -var qa_enabled=true -var qa_data_name=shard-0

# 4. Query (8M first)
QA=$(terraform output -raw qa_url); TOK=$(gcloud auth print-identity-token)
curl -s -m 900 -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
  -d '{"query":"Which entities filed a joint modern slavery statement with Woolworths?","top_k":5}' "$QA/answer"

# 5. Swap checkpoints (rolls a new revision) and re-run the same query set
terraform apply -var qa_enabled=true -var qa_data_name=shard-0 -var gfm_model_path=<34M HF id>
```

### Phase 4 checklist

- [ ] `deploy/serve/app.py` handles vLLM auth itself — it mints and
      auto-refreshes ID tokens for `VLLM_AUDIENCE` (no-op off-GCP). Already
      wired; don't "fix" `OPENAI_API_KEY=dummy`, it's a placeholder.
- [ ] First startup downloads **Qwen3-Embedding-8B (~16GB)** + builds stage-2
      embeddings — the startup probe allows ~20 min; don't panic early.
- [ ] Run the SAME fixed query set (5–10 register questions: joint filers,
      sectors, revenue bands, periods) against both checkpoints; compare
      `/retrieve` top-k and `/answer`. Expect 34M to win on multi-hop.
- [ ] Answers must cite real register entities with exact-name matches.

---

## Smoke-testing services by hand

- Every endpoint sits behind Cloud Run IAM. `gcloud auth print-identity-token`
  works **only if your user is in `extra_invoker_members`** (or you grant
  `roles/run.invoker` manually). A 401 in under a second = bad/empty token or
  missing invoker, NOT a cold start.
- If scripting through layered shells (e.g. `wsl.exe` wrappers), beware
  `$(...)` being eaten by the outer shell → empty `Authorization: Bearer ` →
  401. Put the test in a script file and run the file.

## Teardown checklist

- [ ] `corpus-tuples/` has everything you want to keep — the bucket has
      `force_destroy = true` and **dies with the stack**
- [ ] `terraform destroy` (cluster-free: it's all Cloud Run, so this is fast)
- [ ] Post-destroy cost: Artifact Registry images + build cache only
      (single-digit A$/month; delete the AR repos too for true zero)

## Known limits to respect

| Limit | Value | Consequence |
|---|---|---|
| GPU job task timeout | 3600s (platform cap) | Shards must extract in <1h |
| ID-token lifetime | 1h | Same bound; aligned with the above |
| GPU service max instances | ≤ regional L4 allocation | Raise via quota request |
| One GPU per Cloud Run instance | 1×L4 | 7B-class models max; multi-GPU = GKE |
| Cloud Run filesystem | RAM-backed, counts against memory | Model downloads eat the 32GiB cap; why 3B first |
| Scale-to-zero | weights re-download per cold start | Warm before batch runs; `min_instances=1` during heavy use |
