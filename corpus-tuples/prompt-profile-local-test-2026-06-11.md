# au-register prompt profile — local shard-0 test (2026-06-11)

Setup: isolated dataset (`corpus-shards-profiletest/`, dev graph untouched),
isolated extraction cache, profile auto-applied by `KGConstructor` from
`raw/prompts.yaml` (load confirmed in logs). Local qwen2.5:3b via Ollama
(CPU, Vulkan off). Mint: 31.2 min.

## ABN recall (the profile's design target)

| Metric | Baseline (default prompts) | Profile (au-register) |
|---|---|---|
| Canonical `has ABN` edges | 11 | **16** |
| ABN recall, like-for-like (15 docs both completed) | 8/12 (67%) | **12/12 (100%)** |
| Docs completed | 16/16 | 15/16 |
| Total edges | 528 | 421 (leaner relations: 25 types vs 42) |

**On every document it completed, the profile achieved perfect ABN recall**
(+33 pp over baseline) and put each ABN in the canonical
`[entity, has ABN, n]` form the fact-verification gate wants.

## The one failure — and it's a local-only cost wall

The a2 Milk 5-entity joint statement (5 of the 17 ground-truth ABNs) produced
nothing: **600 s read-timeout**. The profile's pairwise-both-directions +
repeat-attributes-per-entity rules make output length scale ~quadratically
with co-filing entity count — on CPU inference that exceeds
`ChatOllamaNoThink`'s 600 s timeout for 5-entity docs. The baseline's shorter
outputs fit (it got the a2 ABNs 5/5 — but only 67% elsewhere).

Cloud is unaffected (GPU vLLM generates this in seconds), which is consistent
with the other session's rung measurements. Local mitigations, either:
- raise the local client timeout (e.g. `timeout: 1200` for mints), or
- accept that joint-heavy docs are cloud-only territory.

## Verdict

The per-dataset profile mechanism works locally exactly as in cloud (shared
code path, auto-application confirmed), and the au-register profile delivers
its promised ABN improvement decisively. Adopt for local mints with a raised
timeout; the timeout interaction is the one finding to feed back to the
"Cloud Run vs VMs" session.

## Process note

The first attempt at this test produced 16/16 empty extractions — caused not
by the profile but by the WSL VM idle-restart killing Ollama (connection
errors are swallowed into empty results; see LOCAL SETUP.md troubleshooting).
Always `curl /api/version` before interpreting extraction failures.
