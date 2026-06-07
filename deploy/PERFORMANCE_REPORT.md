# GFM-RAG Tuple Extractor — Performance Report

**Date:** 2026-06-07
**Scope:** Local LLM backend selection for the gfmrag OpenIE tuple extractor (NER +
triple extraction), plus cloud (vLLM-on-GCP) deployment recommendations and a
price/performance analysis.

---

## 1. Test environment

| | |
|---|---|
| Hardware | NVIDIA **GTX 960M** (Maxwell, compute 5.0, ~2–4 GB VRAM) — heavily CPU-offloaded |
| OS / runtime | WSL2 (Ubuntu), Python 3.12.13, torch 2.8.0+cu128 |
| LLM server (local) | Ollama 0.30.6 (rootless, `~/.local/bin`) |
| Pipeline | `gfmrag.graph_index_construction.openie_model.LLMOPENIEModel` |
| Test input | Fixed ~95-word biographical passage (Clarence "Fred" Gehrke) |
| Backend | Ollama via the in-repo `ChatOllamaNoThink` client (`think:false`) |

> ⚠️ **Read these numbers as *relative*, not absolute.** The 960M is the bottleneck;
> everything is largely CPU-bound. Times carry model-load overhead and run-to-run
> variance (treat ±20 s as noise). **Structure quality and entity/triple counts are
> the durable signals**, not raw seconds.

---

## 2. Code fixes that materially affected results

Two parser bugs and one performance lever were fixed during testing; the benchmark
numbers below reflect the *fixed* pipeline.

1. **NER bare-array parsing** — Ollama models return NER as a bare JSON array
   (`["a","b"]`), but `extract_json_dict` matched objects only and dropped it.
   Fixed to also accept a top-level array.
2. **Triples bare-list parsing** — models return either `{"triples":[...]}` or a
   bare `[[...]]`; `__call__` now accepts both. Before this fix, qwen2.5:3b
   silently produced **0 triples** despite extracting them correctly.
3. **`think:false` (Ollama)** — wired a `ChatOllamaNoThink` client that calls
   `/api/chat` with `think:false`, since langchain's wrappers can't toggle it and
   Qwen3's `/no_think` soft switch is ignored by this build.

---

## 3. The thinking-mode lever (Qwen3)

Isolated single NER call, qwen3:1.7b, raw `/api/chat`:

| `think` | Wall time | Output tokens | Thinking chars |
|---------|-----------|---------------|----------------|
| `false` | **5.4 s** | 32 | 0 |
| `true` | 69.9 s | 443 | 1,688 |
| unset (**default**) | 98.4 s | 623 | 2,224 |

**Disabling thinking was ~18× faster.** Full-pipeline confirmation: qwen3:1.7b with
thinking **ON** took **772 s** and produced **9 entities / 0 triples** (the triple
call timed out) vs **116 s / 11 / 10** with thinking off — i.e. thinking was *slower
AND less accurate*. **Conclusion: thinking is pure downside for structured extraction.**

---

## 4. Model benchmark (same passage, thinking off, via repo pipeline)

| Model | Params | Wall time | Entities | Triples | Structure quality |
|-------|--------|-----------|----------|---------|-------------------|
| **qwen3:1.7b** | 1.7B | **115.8 s** | 11 | 10 | Clean; reversed one relation direction |
| **gemma2:2b** | 2B | 168.1 s | **16** | 9 | **Clean 3-tuples, correct relations** |
| qwen2.5:3b | 3B | 156.7 s | 11 | 10 | Clean, correct relations |
| phi3.5 | 3.8B | 210.9 s | 13 | 10\* | ❌ Malformed (prose, 1–2 elem "triples") |
| qwen2.5:7b-instruct | 7B | ~317 s | 16 | 13 | Best overall completeness |
| qwen3:4b | 4B | 1201 s | 0 | 0 | ❌ Timed out — not viable on 960M |
| qwen3:1.7b *(think ON)* | 1.7B | 772.4 s | 9 | 0 | ❌ Thinking degraded output |

\* phi3.5's triples passed the count but are structurally invalid (see §5).

**OpenAI `gpt-4o-mini` (intended baseline):** could **not** be benchmarked — the API
key authenticated but the account returned `429 insufficient_quota` (no credits).
Reference benchmark scores: MMLU 82.0, GPQA 40.2, MATH 70.2, HumanEval 87.2.

---

## 5. Per-model notes

- **gemma2:2b — best small-model pick.** At 2B it matched the 7B's **entity recall
  (16)** in roughly half the time, with **well-formed 3-tuples and correct relation
  directions**. Minor flaw: a couple of triples use a date as the subject
  (`['1948','painted','Los Angeles Rams logo']`).
- **qwen3:1.7b — fastest viable.** Solid 11/10, but reversed the great-grandfather
  relation. Best when latency matters most.
- **qwen2.5:3b — balanced.** Correct relations, clean, mid speed.
- **phi3.5 — not recommended for this task.** Slowest of the small models *and*
  emits prose instead of `[subject, relation, object]`, e.g.
  `['Chicago Cardinals players included Fred Gehrke from 1940 to 1950']`. A clear
  reminder that **general benchmarks (phi3.5 ≈ 7B-level on MMLU) do not predict
  structured-extraction quality.**
- **qwen2.5:7b — accuracy leader** (13 triples), at ~2–3× the latency.
- **qwen3:4b — infeasible on a 960M** (VRAM thrash → 600 s timeouts).

---

## 6. Recommendations

### Local (development)
**Default → `gemma2:2b`** (set in `scripts/test_ollama_qwen_tupler.sh`,
`deploy/config/llm_backend.example.env`, and the ollama test): best entity recall
and cleanest triples among small models. Use **`qwen3:1.7b`** when you want the
fastest turnaround. **Always disable thinking.** Avoid phi3.5 and anything ≥4B on
this GPU.

### Cloud (production / hyperscale) — vLLM on GCP
- **Model:** **Qwen2.5-7B-Instruct** (non-thinking) — the throughput/accuracy sweet
  spot; you get the 7B's superior completeness (13 triples) without the local-hardware
  latency penalty. Step up to Qwen2.5-14B / Qwen3-14B only if you need gpt-4o-mini-level
  general accuracy.
- **Serving engine:** **vLLM** (continuous batching + paged attention) — 10–100× the
  throughput of Ollama. This is the real hyperscale lever, more than the model choice.
- **GPU:** 1× **NVIDIA L4** (`g2-standard-8`) with **FP8/AWQ** quantization — the
  cost/throughput sweet spot for ≤7B. A100/H100 only for larger models or strict latency.
- **Guided/JSON-schema decoding** (`--guided-decoding-backend outlines`): force valid
  triple JSON. This would have *eliminated* phi3.5's malformed output and hardens the
  pipeline against the parser edge cases we hit. **Strongly recommended at scale.**
- **Topology:** GKE + autoscaled GPU node pool; extraction as a sharded **Indexed Job**
  (CPU pods) driving the vLLM endpoint, which autoscales via HPA. (See `deploy/`.)

---

## 7. Price–performance commentary (vLLM cloud)

> Figures are **approximate**, US-region on-demand, and move over time / by commitment.
> Validate with the GCP Pricing Calculator and a real load test before budgeting.

**Indicative GCP GPU cost (on-demand):**

| Option | ~Cost/hr | Good for |
|--------|----------|----------|
| `g2-standard-8` (1× L4) | ~$0.85 | 7B–14B serving — **recommended** |
| same, **Spot/Preemptible** | ~$0.25–0.35 | batch extraction, fault-tolerant |
| `a2-highgpu-1g` (1× A100 40GB) | ~$3.7 | larger models / low latency |

**Throughput → cost-per-token logic:** with continuous batching, a 7B (quantized) on
one L4 sustains roughly **hundreds–thousands of output tok/s aggregate** under load.

- Break-even vs **gpt-4o-mini** (~$0.60 / 1M output tokens): an on-demand L4 ($0.85/hr)
  beats the API once you sustain **≳ ~400 output tok/s** (= ~1.4M tok/hr). A batched 7B
  on L4 clears that comfortably **when busy**.
- On **Spot** (~$0.30/hr) the break-even drops to **~140 tok/s** — self-hosting wins in
  almost any non-trivial sustained workload.

**The decision rule:**

| Workload shape | Cheapest choice |
|----------------|-----------------|
| **High, sustained** volume (corpus indexing, hyperscale extraction) | **Self-host vLLM** (Spot L4 + autoscale) — lowest $/token |
| **Low / spiky / bursty** volume | **Managed API** (gpt-4o-mini) — no idle-GPU cost |
| **Batch, fault-tolerant** | **Spot GPUs + scale-to-low**, queue-depth autoscaling |

**Why self-hosting wins for *this* job:** corpus extraction is high-volume, batchable,
and latency-tolerant — exactly where an always-warm batched GPU amortizes best, and
where per-call API pricing is most expensive. The trap is **idle GPU cost**: a serving
endpoint sized for peak but mostly idle is worse than an API. Mitigate with HPA +
scale-to-low (or scale-to-zero for spiky online traffic) and Spot for batch.

**Net:** for sustained extraction, **vLLM + Qwen2.5-7B on Spot L4s** delivers the best
price/performance — typically **well under gpt-4o-mini's per-token cost at high
utilization** — while keeping data in your VPC. Use the managed API only for
low-volume or bursty traffic where idle GPU time would dominate.

---

## 8. Artifacts produced

- Code: `ChatOllamaNoThink` (`langchain_util.py`), bare-list triples fix
  (`llm_openie_model.py`), bare-array NER fix (`utils.py`).
- Local default model → `gemma2:2b`.
- Deploy scaffolding: `deploy/terraform/` (GKE + vLLM + extractor Job + QA service),
  `deploy/docker/Dockerfile{,.serve}`, `deploy/serve/app.py`, `deploy/config/`.
- Plan: `C:\org\gfmrag-deploy.org` (phased, with per-phase test procedures).
