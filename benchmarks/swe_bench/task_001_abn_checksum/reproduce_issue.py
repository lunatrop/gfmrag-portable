#!/usr/bin/env python3
"""SWE-bench Reproduction Script for Issue #142 (ABN Modulus-89 Verification).

Expected Behavior:
- Exits with status code 0 iff Modulus-89 checksum validation is properly implemented.
- Exits with status code 1 on base/unpatched code where 11-digit invalid ABNs are accepted.
"""
import os
import sys

# Ensure repository root is on sys.path regardless of execution directory
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    from scripts.eval.canonicalise_abn import is_valid_abn, validate_abn_checksum
except ImportError as err:
    print(f"FAIL: Missing modular functions in canonicalise_abn: {err}")
    sys.exit(1)

# Valid BHP ABN
VALID_BHP_ABN = "49004028077"
# Single-digit transposition/corruption (length 11, but Modulus-89 fails)
INVALID_CORRUPTED_ABN = "49004028078"

# 1. Valid ABN must pass
if not validate_abn_checksum(VALID_BHP_ABN):
    print(f"FAIL: Legit ABN '{VALID_BHP_ABN}' failed checksum validation.")
    sys.exit(1)

# 2. Corrupted 11-digit ABN MUST FAIL
if validate_abn_checksum(INVALID_CORRUPTED_ABN):
    print(f"FAIL: Corrupted ABN '{INVALID_CORRUPTED_ABN}' was falsely accepted as valid!")
    sys.exit(1)

# 3. is_valid_abn wrapper test
if is_valid_abn(INVALID_CORRUPTED_ABN, check_checksum=True):
    print(f"FAIL: is_valid_abn accepted corrupted ABN '{INVALID_CORRUPTED_ABN}'.")
    sys.exit(1)

print("SUCCESS: ABN Modulus-89 checksum verification is correctly enforced.")
sys.exit(0)
