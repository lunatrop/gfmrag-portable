#!/bin/bash
# Migrate the 4 persistent resources from the compute state into the new
# persistent stack, WITHOUT destroying live infra. Idempotent-ish; stops on error.
set -eu
PROJECT=tautsec-graph-crawler
REGION=us-central1
BUCKET=tautsec-graph-crawler-gfmrag-data
COMPUTE=~/repo/gfm-rag/deploy/cloudrun
PERSIST=$COMPUTE/persistent

echo "=== 1. init persistent stack ==="
cd "$PERSIST" && terraform init -input=false >/dev/null && echo "init ok"

echo "=== 2. import live resources into persistent state ==="
imp() { terraform state list 2>/dev/null | grep -qx "$1" && echo "  $1 already in state" || terraform import -input=false "$1" "$2"; }
imp google_storage_bucket.data "$BUCKET"
imp google_storage_bucket.hf_cache "$BUCKET-hf-cache"
imp google_artifact_registry_repository.gfmrag "projects/$PROJECT/locations/$REGION/repositories/gfmrag"
imp google_artifact_registry_repository.dockerhub "projects/$PROJECT/locations/$REGION/repositories/dockerhub"

echo "=== 3. plan persistent (expect: in-place force_destroy true->false only, NO destroy/create) ==="
terraform plan -input=false -no-color 2>&1 | grep -E "^Plan:|destroy|forces replacement|prevent_destroy" | head -20
echo "(review above — any 'destroy' or 'replacement' = STOP)"
