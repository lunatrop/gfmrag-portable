#!/bin/bash
# Tier 3: benchmarking-caller E2E + negative auth tests. Full log to LOG.
set -u
ADMIN_SA=gfmrag-terraform@tautsec-graph-crawler.iam.gserviceaccount.com
CALLER=gfmrag-benchmark-caller@tautsec-graph-crawler.iam.gserviceaccount.com
QA=https://gfmrag-qa-olbu7sektq-uc.a.run.app
VLLM=https://gfmrag-vllm-olbu7sektq-uc.a.run.app
KEYFILE=$(mktemp /tmp/caller-key-XXXX.json)
LOG=/tmp/tier3.log
exec > "$LOG" 2>&1

echo "=== 1. warm QA (timed) ==="
WARMTOK=$(gcloud auth print-identity-token --account "$ADMIN_SA" --audiences "$QA")
time curl -s -o /dev/null -w "QA healthz: HTTP %{http_code}\n" -m 1800 \
  -H "Authorization: Bearer $WARMTOK" "$QA/healthz"

echo "=== 2. mint caller key ==="
ADC_TOK=$(gcloud auth application-default print-access-token)
curl -s -X POST "https://iam.googleapis.com/v1/projects/-/serviceAccounts/$CALLER/keys" \
  -H "Authorization: Bearer $ADC_TOK" -H "Content-Type: application/json" \
  -d "{\"privateKeyType\":\"TYPE_GOOGLE_CREDENTIALS_FILE\"}" > /tmp/keyresp.json
python3 -c "import json,base64;d=json.load(open('/tmp/keyresp.json'));open('$KEYFILE','w').write(base64.b64decode(d['privateKeyData']).decode())"
KEY_NAME=$(python3 -c "import json;print(json.load(open('/tmp/keyresp.json'))['name'])")
echo "key bytes: $(wc -c < "$KEYFILE")  name: $KEY_NAME"
python3 -c "import json;k=json.load(open('$KEYFILE'));print('keyfile valid:',k.get('type'),k.get('client_email'))"

echo "=== 3. activate (retry for key propagation) ==="
for i in 1 2 3 4 5; do
  if gcloud auth activate-service-account --key-file="$KEYFILE"; then
    echo "activated on attempt $i"; break
  fi
  echo "activate attempt $i failed, sleeping 10s"; sleep 10
done

echo "=== 4. caller flow: /answer, /retrieve, vLLM ==="
CTOK=$(gcloud auth print-identity-token --account "$CALLER" --audiences "$QA")
curl -s -m 900 -H "Authorization: Bearer $CTOK" -H "Content-Type: application/json" \
  -d "{\"query\":\"What industry sectors does NICK SCALI LIMITED operate in?\",\"top_k\":3}" \
  "$QA/answer" | head -c 400
echo; curl -s -m 900 -o /dev/null -w "retrieve: HTTP %{http_code}\n" \
  -H "Authorization: Bearer $CTOK" -H "Content-Type: application/json" \
  -d "{\"query\":\"Adelaide Airport\",\"top_k\":3}" "$QA/retrieve"
CVTOK=$(gcloud auth print-identity-token --account "$CALLER" --audiences "$VLLM")
curl -s -m 60 -o /dev/null -w "vllm health as caller: HTTP %{http_code}\n" \
  -H "Authorization: Bearer $CVTOK" "$VLLM/health"

echo "=== 5. negative tests ==="
curl -s -o /dev/null -w "anonymous /answer: HTTP %{http_code}\n" -m 30 \
  -H "Content-Type: application/json" -d "{\"query\":\"x\"}" "$QA/answer"
curl -s -o /dev/null -w "garbage token:     HTTP %{http_code}\n" -m 30 \
  -H "Authorization: Bearer not-a-real-token" "$QA/answer"
echo "--- caller must NOT read buckets ---"
gcloud storage ls gs://tautsec-graph-crawler-gfmrag-data --account "$CALLER" 2>&1 | tail -1
gcloud storage ls gs://tautsec-graph-crawler-gfmrag-data-hf-cache --account "$CALLER" 2>&1 | tail -1

echo "=== 6. cleanup ==="
gcloud config set account "$ADMIN_SA" 2>&1 | tail -1
gcloud auth revoke "$CALLER" 2>&1 | tail -1 || true
curl -s -X DELETE "https://iam.googleapis.com/v1/$KEY_NAME" \
  -H "Authorization: Bearer $ADC_TOK" -o /dev/null -w "key delete: HTTP %{http_code}\n"
rm -f "$KEYFILE" /tmp/keyresp.json
echo "TIER3_DONE"
