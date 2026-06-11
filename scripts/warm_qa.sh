#!/bin/bash
# Warm the QA + vLLM services to true steady state, with status messages, then
# (optionally) measure latency. Use before a benchmarking batch so requests
# measure inference speed — not cold start — and never hit the cold-vLLM 503.
#
# Warm-up has THREE layers (all required):
#   1. instance up        — Cloud Run scale-from-zero
#   2. models loaded      — gated by QA /openapi.json == 200 (NOT /healthz; see
#                           CLOUD RUN SETUP.md, /healthz is 404'd by the CR layer)
#   3. first-query lazy init — ColBERT PLAID index + first GPU embedding pass;
#                           costs ~70s on the FIRST /retrieve even when 1+2 done.
#
# Usage: warm_qa.sh [--measure]
set -u
SA=${WARM_SA:-gfmrag-terraform@tautsec-graph-crawler.iam.gserviceaccount.com}
QA=https://gfmrag-qa-olbu7sektq-uc.a.run.app
VLLM=https://gfmrag-vllm-olbu7sektq-uc.a.run.app
QTOK=$(gcloud auth print-identity-token --account "$SA" --audiences "$QA")
VTOK=$(gcloud auth print-identity-token --account "$SA" --audiences "$VLLM")
Q='{"query":"warmup probe","top_k":3}'

poll() { # name url tok path
  echo ">>> WARMING UP: $1 ..."
  for i in $(seq 1 60); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' -m 60 -H "Authorization: Bearer $3" "$2$4")" = "200" ] \
      && { echo ">>> $1 ready (~$((i*10))s)"; return 0; }
    sleep 10
  done
  echo ">>> $1 FAILED to warm"; return 1
}

poll "vLLM (model loaded)" "$VLLM" "$VTOK" "/health"
poll "QA (index loaded)"   "$QA"   "$QTOK" "/openapi.json"

echo ">>> WARMING UP: first-query lazy init (ColBERT/embeddings, ~70s)..."
t=$(curl -s -o /dev/null -w '%{time_total}' -m 300 -H "Authorization: Bearer $QTOK" \
     -H "Content-Type: application/json" -d "$Q" "$QA/retrieve")
echo ">>> fully warm — first /retrieve took ${t}s"

if [ "${1:-}" = "--measure" ]; then
  echo "=== steady-state latency (3 reps) ==="
  M='{"query":"What industry sectors does NICK SCALI LIMITED operate in?","top_k":5}'
  for r in 1 2 3; do
    echo "retrieve #$r: $(curl -s -o /dev/null -w '%{time_total}s' -m 300 -H "Authorization: Bearer $QTOK" -H 'Content-Type: application/json' -d "$M" "$QA/retrieve")"
  done
  for r in 1 2 3; do
    echo "answer   #$r: $(curl -s -o /dev/null -w '%{time_total}s' -m 300 -H "Authorization: Bearer $QTOK" -H 'Content-Type: application/json' -d "$M" "$QA/answer")"
  done
fi
