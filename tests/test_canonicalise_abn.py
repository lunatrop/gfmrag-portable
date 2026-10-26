# tests/test_canonicalise_abn.py
"""Comprehensive Unit and Property-Based Test Suite for ABN Canonicalisation.

Validates:
1. Australian Taxation Office (ATO) Modulus-89 checksum math.
2. Robust parsing across arbitrary punctuation, whitespace, and formatting variants.
3. Graph-level entity unification, frequency-based leader election, and conflict resolution.
4. Property-based invariants (idempotence, non-transitivity) using Hypothesis.
"""
from __future__ import annotations

import csv
from typing import List, Tuple

import pytest
from hypothesis import given, strategies as st

from scripts.eval.canonicalise_abn import (
    ABN_WEIGHTS,
    build_canonical_map,
    canonicalise_dataset,
    is_valid_abn,
    norm_abn,
    validate_abn_checksum,
)

# Authentic Australian Corporate ABNs (verified against the Australian Business Register)
REAL_ABNS = [
    ("49004028077", "BHP Group Limited"),
    ("48123123124", "Commonwealth Bank of Australia"),
    ("88000014675", "Woolworths Group Limited"),
    ("33051775556", "Telstra Corporation Limited"),
    ("53102443916", "Atlassian Pty Ltd"),
    ("96004458404", "Rio Tinto Limited"),
]


# =====================================================================
# 1. Modulus-89 Algorithm & Formatting Unit Tests
# =====================================================================

@pytest.mark.parametrize("abn,company", REAL_ABNS)
def test_real_world_abn_checksum_validity(abn: str, company: str) -> None:
    """Authentic real-world corporate ABNs must pass Modulus-89 validation."""
    assert validate_abn_checksum(abn) is True, f"Failed for {company}: {abn}"
    assert is_valid_abn(abn, check_checksum=True) is True


@pytest.mark.parametrize("formatted_variant", [
    "49 004 028 077",
    "49-004-028-077",
    "ABN: 49004028077",
    "(ABN 49 004 028 077)",
    "  49.004.028.077\n",
])
def test_norm_abn_formatting_variants(formatted_variant: str) -> None:
    """norm_abn must strip arbitrary whitespace, prefixes, and punctuation."""
    assert norm_abn(formatted_variant) == "49004028077"


@pytest.mark.parametrize("invalid_input", [
    "",
    None,
    "12345",
    "4900402807",          # 10 digits (too short)
    "490040280771",        # 12 digits (too long)
    "abcdefghijk",         # 11 non-digit chars
    "4900402807a",         # 10 digits + 1 letter
])
def test_norm_abn_invalid_inputs(invalid_input: str | None) -> None:
    """Non-11-digit inputs must evaluate to None."""
    assert norm_abn(invalid_input) is None
    assert is_valid_abn(invalid_input) is False


def test_modulus_89_detects_single_digit_transposition() -> None:
    """Modulus-89 checksum must fail when a single digit is altered or swapped."""
    valid_abn = "49004028077"
    assert validate_abn_checksum(valid_abn) is True

    # Alter single digit
    mutated_digit = "49004028078"
    assert validate_abn_checksum(mutated_digit) is False

    # Swap adjacent digits (04 -> 40)
    transposed = "49040028077"
    assert validate_abn_checksum(transposed) is False


# =====================================================================
# 2. Graph Unification & Leader Election Tests
# =====================================================================

def test_canonical_map_collapses_variants_to_most_frequent() -> None:
    """Surface forms sharing the same ABN must collapse into the most frequent variant."""
    edges: List[Tuple[str, str, str]] = [
        # BHP variants
        ("BHP Group", "has abn", "49004028077"),
        ("BHP Group", "operates in", "Mining"),
        ("BHP Group", "operates in", "Resources"),
        ("BHP GROUP LIMITED", "has abn", "49004028077"),
        ("BHP GROUP LIMITED", "located in", "Melbourne"),
        ("BHP Billiton Ltd", "has abn", "49004028077"),
        # Separate company
        ("Telstra Corp", "has abn", "33051775556"),
    ]

    canon, name_freq, num_abns, conflicts = build_canonical_map(edges)

    assert num_abns == 2
    assert conflicts == 0
    # "BHP Group" has higher frequency than "BHP GROUP LIMITED" and "BHP Billiton Ltd"
    assert canon.get("BHP GROUP LIMITED") == "BHP Group"
    assert canon.get("BHP Billiton Ltd") == "BHP Group"
    assert "BHP Group" not in canon  # Leader is never mapped to anything else
    assert "Telstra Corp" not in canon  # Singleton ABN: not mapped


def test_canonical_map_excludes_conflicting_ambiguous_abns() -> None:
    """Entities linked to multiple distinct ABNs must be marked as conflicts and skipped."""
    edges: List[Tuple[str, str, str]] = [
        ("Ambiguous Holdings", "has abn", "49004028077"),
        ("Ambiguous Holdings", "has abn", "33051775556"),  # Conflicting second ABN
        ("Legit Partner", "has abn", "49004028077"),
    ]

    canon, name_freq, num_abns, conflicts = build_canonical_map(edges)
    assert conflicts == 1
    # "Ambiguous Holdings" must not be collapsed
    assert "Ambiguous Holdings" not in canon


def test_full_dataset_canonicalisation_pipeline(tmp_path) -> None:
    """Verifies end-to-end rewrite of nodes, edges, relations with duplicate/self-loop elimination."""
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()

    # Create dummy nodes.csv
    nodes_file = src_dir / "nodes.csv"
    with open(nodes_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "type", "attributes"])
        w.writerow(["BHP Group", "entity", "{}"])
        w.writerow(["BHP GROUP LIMITED", "entity", "{}"])
        w.writerow(["Mining Sector", "concept", "{}"])

    # Create dummy edges.csv
    edges_file = src_dir / "edges.csv"
    with open(edges_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source", "relation", "target"])
        w.writerow(["BHP Group", "has abn", "49004028077"])
        w.writerow(["BHP GROUP LIMITED", "has abn", "49004028077"])
        w.writerow(["BHP Group", "belongs to", "Mining Sector"])
        w.writerow(["BHP GROUP LIMITED", "belongs to", "Mining Sector"])  # Will become duplicate
        w.writerow(["BHP GROUP LIMITED", "subsidiary of", "BHP Group"])  # Will become self-loop

    # Create dummy relations.csv
    relations_file = src_dir / "relations.csv"
    relations_file.write_text("relation\nhas abn\nbelongs to\nsubsidiary of\n", encoding="utf-8")

    stats = canonicalise_dataset(str(src_dir), str(dst_dir))

    assert stats["nodes_in"] == 3
    assert stats["nodes_out"] == 2  # "BHP Group" and "Mining Sector"
    assert stats["duplicates_dropped"] == 2
    assert stats["self_loops_dropped"] == 1


# =====================================================================
# 3. Property-Based Tests (Hypothesis)
# =====================================================================

@given(st.text())
def test_norm_abn_never_crashes_on_arbitrary_strings(random_text: str) -> None:
    """norm_abn must never throw an unhandled exception regardless of input noise."""
    res = norm_abn(random_text)
    if res is not None:
        assert len(res) == 11
        assert res.isdigit()


@given(st.text(alphabet="0123456789 -./", min_size=11, max_size=25))
def test_norm_abn_idempotent_on_valid_extractions(raw_input: str) -> None:
    """Repeated normalisation on an already extracted ABN is invariant."""
    cleaned = norm_abn(raw_input)
    if cleaned is not None:
        assert norm_abn(cleaned) == cleaned


@given(st.lists(st.tuples(
    st.text(min_size=1, max_size=10, alphabet="abcdefghij"),
    st.just("has abn"),
    st.sampled_from(["49004028077", "48123123124", "88000014675"])
), min_size=1, max_size=30))
def test_canonical_map_no_transitive_cycles(edges) -> None:
    """Property: The canonical map must be strictly single-hop (no transitive remappings)."""
    canon, _, _, _ = build_canonical_map(edges)
    for variant, leader in canon.items():
        assert variant != leader
        # The chosen leader must NEVER be remapped itself
        assert leader not in canon, f"Cycle/transitive mapping detected: {leader} in canon"
