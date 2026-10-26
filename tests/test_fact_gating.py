# tests/test_fact_gating.py
"""Unit and Property-Based Tests for the Deterministic Fact-Gating Oracle.

Validates:
1. Verification of grounded triples with authentic Australian corporate ABNs.
2. Immediate rejection and scoring penalties for hallucinated/corrupt ABN checksums.
3. Accurate recall and precision metrics across multi-entity filings.
4. Property-based invariants ensuring bounded reward signals in [0.0, 1.0].
"""
from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from scripts.eval.fact_gate import FactGateOracle, FactGateResult, normalise_text


# Known ground truth register fixture
@pytest.fixture
def sample_oracle() -> FactGateOracle:
    known_entities = {
        "BHP Group Limited",
        "Woolworths Group Limited",
        "Mining Sector",
        "Retail Sector",
    }
    known_abns = {
        "49004028077",  # BHP
        "88000014675",  # Woolworths
    }
    return FactGateOracle(
        known_entities=known_entities,
        known_abns=known_abns,
        min_recall_threshold=0.5,
    )


# =====================================================================
# 1. Oracle Verification & Reward Tests
# =====================================================================

def test_fact_gate_verifies_valid_grounded_triples(sample_oracle: FactGateOracle) -> None:
    """Accurately extracted triples with valid ABNs must pass verification with high reward."""
    triples = [
        ("BHP Group Limited", "has abn", "49 004 028 077"),
        ("BHP Group Limited", "operates in", "Mining Sector"),
    ]
    expected_abns = {"49004028077"}

    result: FactGateResult = sample_oracle.verify_triples(triples, expected_abns=expected_abns)

    assert result.is_verified is True
    assert result.abn_recall == 1.0
    assert result.abn_precision == 1.0
    assert result.reward_score == 1.0
    assert len(result.invalid_abns) == 0
    assert len(result.hallucinated_entities) == 0


def test_fact_gate_rejects_hallucinated_abn_checksum(sample_oracle: FactGateOracle) -> None:
    """An invented or single-digit-corrupted ABN must be caught and rejected by the oracle."""
    corrupted_abn = "49004028078"  # Fails Modulus-89
    triples = [
        ("BHP Group Limited", "has abn", corrupted_abn),
    ]
    expected_abns = {"49004028077"}

    result = sample_oracle.verify_triples(triples, expected_abns=expected_abns)

    assert result.is_verified is False
    assert corrupted_abn in result.invalid_abns
    assert result.abn_recall == 0.0
    assert result.reward_score == 0.0  # Penalized
    assert any("Modulus-89" in v for v in result.violations)


def test_fact_gate_computes_partial_recall(sample_oracle: FactGateOracle) -> None:
    """When only 1 of 2 expected ABNs is recovered, recall must reflect exactly 0.5."""
    triples = [
        ("BHP Group Limited", "has abn", "49004028077"),
    ]
    # Expecting both BHP and Woolworths in this multi-entity statement
    expected_abns = {"49004028077", "88000014675"}

    result = sample_oracle.verify_triples(triples, expected_abns=expected_abns)

    assert result.abn_recall == 0.5
    assert result.abn_precision == 1.0
    assert result.is_verified is True  # Meets 0.5 threshold


def test_fact_gate_flags_ungrounded_entity_names(sample_oracle: FactGateOracle) -> None:
    """Extracted entities that do not exist in the official register must be flagged."""
    triples = [
        ("BHP Group Limited", "has abn", "49004028077"),
        ("Fabricated Company XYZ", "operates in", "Mining Sector"),
    ]

    result = sample_oracle.verify_triples(triples, expected_abns={"49004028077"})

    assert "fabricated company xyz" in result.hallucinated_entities
    assert any("ungrounded entities" in v for v in result.violations)


# =====================================================================
# 2. Property-Based Testing (Hypothesis)
# =====================================================================

@given(st.lists(
    st.tuples(
        st.text(min_size=1, max_size=15),
        st.sampled_from(["has abn", "operates in", "located in", "subsidiary of"]),
        st.text(min_size=1, max_size=20),
    ),
    max_size=20,
))
def test_reward_score_bounded_between_zero_and_one(triples) -> None:
    """Property: Regardless of hallucinated noise, reward score must remain strictly in [0.0, 1.0]."""
    oracle = FactGateOracle(min_recall_threshold=0.5)
    result = oracle.verify_triples(triples)

    assert 0.0 <= result.reward_score <= 1.0
    assert 0.0 <= result.abn_recall <= 1.0
    assert 0.0 <= result.abn_precision <= 1.0
