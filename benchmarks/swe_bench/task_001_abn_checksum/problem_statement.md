# Issue: Incomplete ABN Validation Merges Checksum-Corrupted Entities in Canonicalisation

## Description
In `scripts/eval/canonicalise_abn.py`, the `norm_abn` utility currently only verifies string length (`len(digits) == 11`).

During entity canonicalisation across extracted corporate register statements, typographical extraction errors (such as single-digit transpositions or LLM hallucinations) that produce an 11-digit string are mistakenly accepted as valid Australian Business Numbers. This leads to improper merging of unrelated corporate nodes in the knowledge graph.

### Expected Behavior
The Australian Taxation Office (ATO) defines an exact mathematical checksum for all legitimate Australian Business Numbers based on a **Modulus-89 weighting algorithm**:

1. Subtract 1 from the first digit.
2. Multiply each of the 11 digits by its positional weight from the vector:
   `[10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19]`
3. Sum the products.
4. Validate that `sum % 89 == 0`.

The canonicalisation pipeline must enforce Modulus-89 checksum verification. Any extracted ABN candidate that fails the Modulus-89 test must be rejected as invalid rather than assigned to an entity node.

### Reproduction Steps
Execute `reproduce_issue.py`. On the base implementation, invalid ABN candidate `"49004028078"` (a single-digit mutation of BHP's legitimate ABN `"49004028077"`) is treated as valid, causing an assertion failure in the reproduction test.
