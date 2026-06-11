#!/bin/bash
set -eu
COMPUTE=~/repo/gfm-rag/deploy/cloudrun
PERSIST=$COMPUTE/persistent

echo "=== 1. apply persistent (force_destroy->false in place) ==="
cd "$PERSIST" && terraform apply -auto-approve -input=false -no-color 2>&1 | grep -E "^Apply complete|Error" | head -3

echo "=== 2. remove the 4 from COMPUTE state (they live in persistent now) ==="
cd "$COMPUTE"
for r in google_storage_bucket.data google_storage_bucket.hf_cache \
         google_artifact_registry_repository.gfmrag google_artifact_registry_repository.dockerhub; do
  terraform state list 2>/dev/null | grep -qx "$r" && terraform state rm "$r" || echo "  $r not in compute state (ok)"
done

echo "=== 3. validate + plan compute (expect: NO destroy of buckets/AR; data sources read) ==="
terraform validate
terraform plan -input=false -no-color -var qa_enabled=true 2>&1 | grep -E "^Plan:|will be destroyed|will be created|must be replaced|Error:" | head -25
echo "(any bucket/AR destroy or replace above = STOP and report)"
