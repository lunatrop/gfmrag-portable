# Deploy: vLLM on GCP (hyperscale) + Ollama locally

Scaffolding to serve the gfmrag tuple extractor's LLM two ways from one codebase:

- **Local dev** → **Ollama** (`qwen3:1.7b` / `qwen2.5:7b`), fast and free.
- **Production / hyperscale** → **vLLM on GKE** (autoscaled L4 GPUs), serving an
  OpenAI-compatible endpoint.

The extractor code is identical in both cases — only `llm_api` and the endpoint
change. vLLM speaks the OpenAI API, so the existing `openai` backend points at it.

```
        ┌─────────────────────────┐
        │  LLMOPENIEModel /        │   llm_api=ollama  ┌──────────────┐
        │  LLMNERModel  (gfmrag)   │ ────────────────▶ │ Ollama :11434│  (local)
        │                          │                   └──────────────┘
        │                          │   llm_api=openai  ┌──────────────────────────┐
        │                          │ ────────────────▶ │ vLLM /v1 on GKE (L4, HPA)│  (GCP)
        └─────────────────────────┘   OPENAI_BASE_URL  └──────────────────────────┘
```

## Layout
```
deploy/
├── terraform/              # GCP: GKE + GPU node pool + vLLM Deployment/Service/HPA
│   ├── versions.tf         # providers, (optional) GCS remote state
│   ├── variables.tf        # project, region, GPU type, model, replicas
│   ├── main.tf             # cluster + autoscaled L4 node pool + k8s provider
│   ├── vllm.tf             # namespace, HF secret, vLLM deploy, internal LB, HPA
│   ├── outputs.tf          # endpoint URL + kubectl creds command
│   └── terraform.tfvars.example
└── config/
    └── llm_backend.example.env   # local-ollama vs gcp-vllm selector
```

## Deploy to GCP
```bash
cd deploy/terraform
cp terraform.tfvars.example terraform.tfvars   # edit project_id, region
export TF_VAR_hf_token=hf_xxx                   # only for gated models

terraform init
terraform plan
terraform apply

# Get the endpoint (wait ~1 min for the internal LB):
terraform output vllm_openai_base_url
```

Point the extractor at it:
```bash
export GFMRAG_LLM_API=openai
export GFMRAG_MODEL_NAME="$(terraform output -raw served_model_id)"
export OPENAI_BASE_URL="$(terraform output -raw vllm_openai_base_url)"
export OPENAI_API_KEY=dummy
```
Then run the extractor with a hydra override, e.g.:
```bash
python -m gfmrag.workflow.stage1_index_dataset \
  openie_model.llm_api=openai \
  openie_model.model_name="Qwen/Qwen2.5-7B-Instruct" \
  ner_model.llm_api=openai \
  ner_model.model_name="Qwen/Qwen2.5-7B-Instruct"
```

## Run the extractor *on GCP* (batch over a corpus)

The vLLM stack above only serves the LLM. To run the gfmrag extractor itself,
these resources are added:

| Resource | File | Purpose |
|----------|------|---------|
| CPU node pool | `extractor_infra.tf` | Runs the extractor (LLM-API-bound, not GPU) + system pods |
| Artifact Registry | `extractor_infra.tf` | Holds the `extractor` image |
| GCS bucket | `extractor_infra.tf` | Corpus in (`data/shard-N`) + graph-index out |
| Workload Identity SA | `extractor_infra.tf` | Pod → GCS, no keys |
| Indexed Job | `extractor_job.tf` | N parallel pods, one corpus shard each |
| Image | `deploy/docker/Dockerfile` | `python -m gfmrag.workflow.index_dataset` |

Flow:
```bash
# 1. Build + push the image (Terraform prints the exact command):
terraform output -raw image_push_command | bash

# 2. Stage the corpus as shards in the bucket:
#    gsutil -m cp -r ./data/shard-0 gs://$(terraform output -raw data_bucket)/shard-0   (etc.)

# 3. Apply — creates the Indexed Job (parallelism = number of shards):
terraform apply

# 4. Watch it; vLLM's HPA scales up under the load:
kubectl get jobs,pods
kubectl logs -l app=gfmrag-extract --tail=50
```
Each pod runs, sharded by `JOB_COMPLETION_INDEX`:
```
python -m gfmrag.workflow.index_dataset \
  dataset.root=/data dataset.data_name=shard-$JOB_COMPLETION_INDEX \
  openie_model.llm_api=openai openie_model.model_name=Qwen/Qwen2.5-7B-Instruct \
  ner_model.llm_api=openai   ner_model.model_name=Qwen/Qwen2.5-7B-Instruct
```
with `OPENAI_BASE_URL=http://vllm.llm.svc.cluster.local/v1` (in-cluster, no egress).

### Two real caveats
- **Image weight / GPU deps**: `import gfmrag` pulls in torch + `faiss-gpu-cu12`,
  so the image is large and the CPU-only path can hit faiss CUDA import errors.
  For a clean CPU extractor, build a variant that swaps `faiss-gpu-cu12 → faiss-cpu`
  and the CPU torch wheel. The Dockerfile notes this.
- **Full pipeline ≠ just extraction**: `index_dataset` also runs entity linking
  (ColBERT) and the SFT/embedding constructor (Qwen3-Embedding-8B), which want a
  GPU. For *pure* NER+OpenIE, run only those stages (or point embeddings at a
  second vLLM/embedding service and schedule the EL step on the GPU pool).

## Serve a prompting API over the knowledge graph

Once extraction has written the index to GCS, deploy the **prompting service** —
a long-running API (not a batch Job) that loads the GFM checkpoint + the KG index
and answers queries.

| Resource | File | Purpose |
|----------|------|---------|
| FastAPI wrapper | `deploy/serve/app.py` | `/retrieve` + `/answer` around `GFMRetriever` |
| Image | `deploy/docker/Dockerfile.serve` | gfmrag + fastapi/uvicorn |
| Deployment | `qa_service.tf` | GPU pod: loads GFM (8M/34M) + index, calls vLLM |
| Service + HPA | `qa_service.tf` | Internal LB + autoscaling |

```bash
# 1. Build + push the serving image:
terraform output -raw qa_image_push_command | bash

# 2. Apply — creates the gfmrag-qa Deployment/Service/HPA:
terraform apply -var gfm_model_path=rmanluo/GFM-RAG-8M -var qa_data_name=mycorpus
#   (use the 34M G-Reasoner checkpoint instead by changing gfm_model_path)

# 3. Query it (internal IP):
terraform output qa_service_internal_ip
curl -s http://<qa-ip>/answer -H 'Content-Type: application/json' \
  -d '{"query":"Who designed the Rams logo?","top_k":5}'
```

Per request the service runs: NER (→vLLM) → entity-linking (ColBERT) → query
embedding (Qwen3-Embedding-8B) → GFM reasoning over the KG → top-k docs →
answer (→vLLM). The GFM checkpoint is the cheapest part; embeddings + EL are why
the pod needs a GPU.

**8M vs 34M**: identical to deploy — just change `gfm_model_path`. The 34M
G-Reasoner gives better multi-hop quality at near-identical serving cost.

**GPU contention**: this pod needs its own GPU (separate from vLLM). Raise the GPU
pool `max_node_count` or add a dedicated pool so they land on different nodes.

## Run locally (Ollama)
```bash
ollama serve &
ollama pull qwen3:1.7b
python -m gfmrag.workflow.stage1_index_dataset \
  openie_model.llm_api=ollama openie_model.model_name=qwen3:1.7b \
  ner_model.llm_api=ollama   ner_model.model_name=qwen3:1.7b
```

## Why this model / shape
- **Qwen2.5-7B-Instruct** (non-thinking) is the throughput/accuracy sweet spot for
  extraction — see the in-repo benchmarks. Bump `model_id` + GPU for more accuracy.
- **vLLM** gives 10–100× the throughput of Ollama via continuous batching — the
  reason it's the GCP serving engine (and why we *removed* it from local deps).
- **Guided decoding** (`--guided-decoding-backend outlines`) lets you force valid
  JSON, eliminating the bare-list/malformed-JSON parse failures at scale.

## Not production-hardened (intentionally scaffolding)
Before real use, add: private GKE cluster + authorized networks; API Gateway/IAP
auth in front of the internal LB; GCS remote TF state with locking; Workload
Identity binding for the vLLM SA; resource requests/limits + PodDisruptionBudget;
queue-depth-based HPA (Prometheus Adapter on `vllm:num_requests_waiting`) instead
of the CPU placeholder; and image digest pinning.
