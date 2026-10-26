# SWE-bench Task: lunatrop__gfmrag-portable-142

This folder contains a fully formatted, reproducible **SWE-bench task instance** designed for evaluating autonomous software engineering agents (e.g. SWE-agent, Devin, Claude Code) and training RL reward models.

---

### Task Metadata
* **Instance ID**: `lunatrop__gfmrag-portable-142`
* **Repository**: `lunatrop/gfmrag-portable`
* **Target Issue**: Incomplete ABN checksum validation allows hallucinated/corrupt corporate nodes to merge.
* **Domain**: Knowledge Graph Canonicalisation & Australian Taxation Office (ATO) Mathematical Checksum Verification.

---

### File Structure
* **`problem_statement.md`**: The standalone issue description presented to the agent.
* **`instance.json`**: Benchmark metadata compliant with the official SWE-bench harness format.
* **`reproduce_issue.py`**: Automated oracle script that fails on the buggy base commit and passes with the fix.
* **`gold_patch.diff`**: The canonical reference diff resolving the issue.
* **`tests/test_canonicalise_abn.py`**: The corresponding unit and property-based test oracle.

---

### Verification
Run the reproduction oracle:
```bash
python benchmarks/swe_bench/task_001_abn_checksum/reproduce_issue.py
```
Expected output:
```
SUCCESS: ABN Modulus-89 checksum verification is correctly enforced.
```
