# scripts/eval/fact_gate.py
"""Deterministic Fact-Gating Verification Oracle for GFM-RAG.

Evaluates whether model-extracted knowledge triples or generated statements
faithfully reflect ground-truth structured registers, providing verifiable
reward and precision/recall signals for SWE/RL training pipelines.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from scripts.eval.canonicalise_abn import is_valid_abn, norm_abn, validate_abn_checksum


@dataclasses.dataclass
class FactGateResult:
    """Structured verification oracle output for RL reward modeling and benchmark scoring."""
    is_verified: bool
    reward_score: float                     # Scalar metric [0.0, 1.0]
    abn_recall: float                       # Fraction of expected register ABNs captured
    abn_precision: float                    # Fraction of emitted ABNs that are valid & grounded
    hallucinated_entities: List[str]        # Entities with no grounding in register
    invalid_abns: List[str]                 # ABNs failing Modulus-89 checksum or format
    violations: List[str]                   # Human-readable violation explanations


def normalise_text(s: str | None) -> str:
    """Normalize surface form: lowercase, alpha-numeric tokens only."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())


class FactGateOracle:
    """Deterministic Fact Verification Engine over Australian Modern Slavery Register filings."""

    def __init__(
        self,
        known_entities: Optional[Set[str]] = None,
        known_abns: Optional[Set[str]] = None,
        min_recall_threshold: float = 0.5,
    ) -> None:
        self.known_entities: Set[str] = {normalise_text(e) for e in (known_entities or set())}
        self.known_abns: Set[str] = {norm_abn(a) for a in (known_abns or set()) if norm_abn(a)}
        self.min_recall_threshold = min_recall_threshold

    def verify_triples(
        self,
        extracted_triples: List[Tuple[str, str, str]],
        expected_abns: Optional[Set[str]] = None,
    ) -> FactGateResult:
        """Evaluate a set of extracted knowledge graph triples against registered facts.

        Args:
            extracted_triples: List of (source, relation, target) tuples.
            expected_abns: Set of ground-truth ABNs expected for this document context.

        Returns:
            FactGateResult with scores and violations.
        """
        expected_clean: Set[str] = {
            norm_abn(a) for a in (expected_abns or set()) if norm_abn(a)
        }
        emitted_abns: Set[str] = set()
        emitted_entities: Set[str] = set()
        invalid_abns: List[str] = []
        violations: List[str] = []

        # 1. Audit extracted triples
        for src, rel, tgt in extracted_triples:
            clean_src = normalise_text(src)
            if clean_src:
                emitted_entities.add(clean_src)

            rel_lower = rel.strip().lower()
            if rel_lower in {"has abn", "abn"}:
                cleaned_abn = norm_abn(tgt)
                if not cleaned_abn or not validate_abn_checksum(cleaned_abn):
                    invalid_abns.append(tgt)
                    violations.append(f"Invalid ABN Modulus-89 checksum or format: '{tgt}'")
                else:
                    emitted_abns.add(cleaned_abn)
            else:
                clean_tgt = normalise_text(tgt)
                if clean_tgt:
                    emitted_entities.add(clean_tgt)

        # 2. Check for hallucinated / ungrounded entities (if register ground truth is loaded)
        hallucinated: List[str] = []
        if self.known_entities:
            for entity in emitted_entities:
                if entity not in self.known_entities:
                    hallucinated.append(entity)
            if hallucinated:
                violations.append(f"Detected {len(hallucinated)} ungrounded entities: {hallucinated[:3]}")

        # 3. Calculate Precision & Recall
        # ABN Recall: proportion of expected ABNs that were successfully extracted
        if expected_clean:
            recovered_abns = expected_clean.intersection(emitted_abns)
            abn_recall = len(recovered_abns) / len(expected_clean)
        else:
            abn_recall = 1.0 if emitted_abns else 0.0

        # ABN Precision: proportion of emitted ABNs that are mathematically valid and grounded
        total_attempted_abns = len(emitted_abns) + len(invalid_abns)
        if total_attempted_abns > 0:
            if self.known_abns:
                grounded_abns = emitted_abns.intersection(self.known_abns)
                abn_precision = len(grounded_abns) / total_attempted_abns
            else:
                abn_precision = len(emitted_abns) / total_attempted_abns
        else:
            abn_precision = 1.0 if not expected_clean else 0.0

        # 4. Compute composite reward score
        # Penalty for invalid ABN checksums: severe (-0.5 per invalid ABN)
        checksum_penalty = 0.5 * len(invalid_abns)
        raw_score = (0.6 * abn_recall) + (0.4 * abn_precision) - checksum_penalty
        reward_score = max(0.0, min(1.0, raw_score))

        is_verified = (
            len(invalid_abns) == 0
            and abn_recall >= self.min_recall_threshold
            and abn_precision >= 0.5
        )

        return FactGateResult(
            is_verified=is_verified,
            reward_score=round(reward_score, 4),
            abn_recall=round(abn_recall, 4),
            abn_precision=round(abn_precision, 4),
            hallucinated_entities=hallucinated,
            invalid_abns=invalid_abns,
            violations=violations,
        )
