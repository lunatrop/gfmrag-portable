# LOCAL SETUP — running the gfm-rag tests on this machine

Verified end-to-end on 2026-06-10 (WSL2 Ubuntu, GTX 960M, 8M + 34M checkpoints,
shard-0 of the modern-slavery corpus). Results these steps reproduce:
`corpus-tuples/local-8m-test-2026-06-10.md`, `local-34m-test-2026-06-10.md`,
`smoke-test-2026-06-10.md`, `ladder-results.md`.

## The three golden rules on this box

1. **`CUDA_VISIBLE_DEVICES=""` for every torch process.** torch ≥2.8 detects
   the GTX 960M but ships no sm_50 kernels — anything that touches the GPU dies
   with `no kernel image is available`. Only Ollama may use the GPU (its own
   runtime still supports Maxwell).
2. **Put the venv's `bin` on PATH** when launching scripts
   (`export PATH="$HOME/repo/gfm-rag/.venv/bin:$PATH"`). ColBERT JIT-compiles a
   C++ extension at startup and needs `ninja` discoverable — calling
   `.venv/bin/python` directly is not enough.
3. **Start Ollama with `OLLAMA_VULKAN=false`.** Ollama ≥0.30 auto-enables the
   Vulkan backend on the 960M (CUDA needs Windows driver ≥570; this box has
   556) and Vulkan generation is silently broken — query-NER deterministically
   returns `[]` for everything. Symptom of a poisoned server: previously-good
   prompts suddenly extract nothing. Fix: restart with
   `OLLAMA_VULKAN=false ollama serve`. (Updating the Windows NVIDIA driver to
   ≥570 would restore CUDA and make Ollama several-fold faster.)

## 0. One-time prerequisites checklist

- [ ] `poetry install --extras faiss-cpu` completed in `.venv`
      (NOT `faiss-gpu` — see rule 1). Verify: `python -c "import faiss; print(faiss.get_num_gpus())"` → `0`
- [ ] Ollama serving (`curl -sf 127.0.0.1:11434/api/version`) with
      `qwen2.5:3b` pulled (the validated extractor; gemma2:2b fails triples on
      register text)
- [ ] HF models cached (~10.7 GB total — see `big-local-downloads.org` for the
      full dependency tree). Required per test path:
      - 8M path: `rmanluo/GFM-RAG-8M` + `sentence-transformers/all-mpnet-base-v2`
      - 34M path: `rmanluo/G-reasoner-34M` + `Qwen/Qwen3-Embedding-0.6B`
      - both: `colbert-ir/colbertv2.0`; stage-1 minting also pulls `BAAI/bge-large-en-v1.5`
      - When downloading, pass `allow_patterns=["*.json","*.txt","*.safetensors","tokenizer*","1_Pooling/*"]`
        to `snapshot_download` — full snapshots drag GBs of ONNX/TF duplicates.
- [ ] `fastapi` + `uvicorn[standard]` pip-installed (serving test only; they're
      deliberately not in pyproject)
- [ ] Corpus shards exist: `corpus-shards/shard-{0..5}/raw/documents.json`
      (committed; regenerate with
      `python scripts/prepare_corpus_shards.py --out corpus-shards --ladder 16,64,256,1024,4096,rest --seed 42`)

Standard environment prelude for every command below:

```bash
cd ~/repo/gfm-rag
export PATH="$HOME/repo/gfm-rag/.venv/bin:$PATH"
export CUDA_VISIBLE_DEVICES=""
```

## 1. Extractor smoke test (~3 min)

```bash
./scripts/test_ollama_qwen_tupler.sh   # default model qwen2.5:3b
```
- [ ] Pass: non-empty ENTITIES and TRIPLES, well-formed 3-tuples.

## 2. Stage-1 KG mint over shard-0 (~30 min cold, ~4 min cached)

The retriever auto-builds stage-1 when missing, or run it standalone by
instantiating `KGConstructor` (OpenIE `ollama_qwen` profile + ColBERT EL) and
calling `build_graph("corpus-shards", "shard-0")`, then writing
`pd.DataFrame(graph[name])` for `nodes/edges/relations` to
`corpus-shards/shard-0/processed/stage1/` — mirror of
`GFMRetriever.from_index`'s bootstrap (`gfmrag/gfmrag_retriever.py:255`).

- [ ] OpenIE results are cached under `tmp/kg_construction/<fingerprint>/`
      (`force: false`) — a crashed run resumes nearly free.
- [ ] Pass: 3 CSVs written; shard-0 yields ~124 nodes / ~528 edges / 42 relations.

## 3. Retriever + golden queries, 8M checkpoint (~1 min cold, seconds warm)

```python
from hydra.utils import instantiate
from omegaconf import OmegaConf
from gfmrag import GFMRetriever

cfg = "gfmrag/workflow/config"
retriever = GFMRetriever.from_index(
    data_dir="corpus-shards", data_name="shard-0",
    model_path="rmanluo/GFM-RAG-8M",
    ner_model=instantiate(OmegaConf.load(f"{cfg}/ner_model/ollama_qwen.yaml")),
    el_model=instantiate(OmegaConf.load(f"{cfg}/el_model/colbert_el_model.yaml")),
)
results = retriever.retrieve(
    "Which entity is included in NICK SCALI LIMITED's modern slavery statement?",
    top_k=3,
)
for d in results["document"]:
    print(d["score"], d["id"])
```

- [ ] First load builds stage-2 (mpnet embeddings) into
      `processed/stage2/<fingerprint>/`; later loads must log a **load, not a
      rebuild** — a rebuild means the embedder config diverged from the
      checkpoint's.
- [ ] Pass (golden set): Nick Scali statement rank 1 for the query above;
      a2 Milk joint statement rank 1 for "Which companies headquartered in New
      Zealand filed a joint modern slavery statement?".

## 4. 34M G-Reasoner comparison (~4 min cold)

Same as test 3 with `model_path="rmanluo/G-reasoner-34M"`. Notes:
- Builds its **own** stage-2 (Qwen3-Embedding-0.6B @1024-dim, different dataset
  class) — not interchangeable with the 8M's.
- Locally the embedder runs through the sentence-transformers fallback in
  `Qwen3TextEmbModel` (vllm is a cloud-only dep).
- [ ] Expected at this scale: Q1 rank 1, Q2 a2 Milk ~rank 2 (8M outperforms the
      34M on tiny graphs — re-judge at rung 3+).

## 5. Serving layer: /retrieve + /answer (~1 min startup)

```bash
DATA_DIR=corpus-shards DATA_NAME=shard-0 \
GFM_MODEL_PATH=rmanluo/GFM-RAG-8M \
LLM_API=ollama LLM_MODEL=qwen2.5:3b \
OPENAI_BASE_URL=http://127.0.0.1:11434/v1 OPENAI_API_KEY=ollama \
uvicorn app:app --app-dir deploy/serve --host 127.0.0.1 --port 8001
```

```bash
curl -sf 127.0.0.1:8001/healthz          # {"status":"ok"} after ~1 min
curl -sf 127.0.0.1:8001/answer -H 'Content-Type: application/json' \
  -d '{"query":"Which entity is included in NICK SCALI LIMITED'\''s modern slavery statement?","top_k":3}'
```

- [ ] Pass: `/retrieve` ≈17s with Nick Scali rank 1; `/answer` ≈30s returning
      "PLUSH-THINK SOFAS PTY LTD …" grounded in the retrieved docs.
- [ ] Answers route through Ollama's OpenAI-compatible endpoint — both
      `OPENAI_BASE_URL` and `OPENAI_API_KEY` (any value) must be set.

## Troubleshooting — every failure we actually hit

| Symptom | Cause → fix |
|---|---|
| `CUDA error: no kernel image is available` | torch touched the 960M → `CUDA_VISIBLE_DEVICES=""` (rule 1) |
| `RuntimeError: Ninja is required to load C++ extensions` | venv bin not on PATH (rule 2) |
| NER: `'SimpleNamespace' object has no attribute 'response_metadata'` | old code — `ChatOllamaNoThink` missing from the ollama isinstance branch (fixed in `llm_ner_model.py`) |
| Query-NER returns `[]` or chats instead of extracting | small models refuse the multi-turn one-shot format — the ollama branch now uses a single-turn explicit prompt (fixed) |
| 34M load: `ModuleNotFoundError: No module named 'vllm'` | old code — `Qwen3TextEmbModel` now falls back to sentence-transformers locally (fixed) |
| Stage-2 rebuilds on every load | embedder config mismatch vs the checkpoint's `config.json` fingerprint — don't override `text_emb_model_cfgs` |
| gemma2:2b produces 0 triples | known on register-style text — use qwen2.5:3b |
| Background launches silently do nothing | verify the log file exists after launch; don't trust `pgrep -f` (it matches its own command line — use a `[b]racketed` pattern) |
| ALL extractions suddenly return empty entities/triples | **check Ollama is actually up** (`curl -sf 127.0.0.1:11434/api/version`) before blaming prompts or models — the model classes swallow connection errors and return `[]`/empty, so a dead server looks exactly like total extraction failure. The WSL VM shuts down when idle, killing Ollama/uvicorn and wiping `/tmp` (scripts, logs). After any WSL restart: relaunch Ollama with `OLLAMA_VULKAN=false` |
