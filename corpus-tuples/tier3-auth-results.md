# Tier 3 — benchmarking-caller E2E + negative auth (2026-06-11)

Harness: `tmp/tier3.sh`. The caller SA (`gfmrag-benchmark-caller`) is the
credential the tautsec-benchmarking Vercel app uses. PASS on every assertion.

## Positive — the Vercel app's path works
| Call (as caller SA) | Result |
|---|---|
| `/answer` "sectors of NICK SCALI" | 200 — "Retail Trade", source doc retrieved |
| `/retrieve` | 200 |
| vLLM `/health` | 200 |

## Negative — boundary holds
| Test | Result |
|---|---|
| anonymous `/answer` | 403 (rejected) |
| garbage bearer token | 401 (rejected) |
| caller → data bucket `ls` | denied (storage.objects.list) |
| caller → hf-cache bucket `ls` | denied |

Least privilege confirmed: caller has `run.invoker` only — invokes the APIs,
cannot read corpus/tuples/cache in GCS.

## Operational notes
- Fresh SA keys have a propagation lag: activation failed on attempt 1
  (`Invalid JWT Signature`), succeeded on attempt 2 after 10s. The Vercel
  WIF/key path should tolerate one retry on first use.
- Cleanup verified: test key deleted (HTTP 200), admin account restored.
