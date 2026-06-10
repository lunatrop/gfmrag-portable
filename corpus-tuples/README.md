# corpus-tuples

Output directory for tuple-extraction results over `corpus/` (NER + OpenIE
triples: per-shard `nodes.csv`, `edges.csv`, `relations.csv`).

- Local runs write here directly.
- GCP runs write to the Terraform-managed GCS bucket; copy results back here
  **before** `terraform destroy` (the bucket is destroyed with the stack).
