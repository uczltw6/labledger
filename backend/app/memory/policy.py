"""Deterministic validity annotation and transparent retrieval reranking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.app.memory.models import MemoryStatus, RetrievalContext, VectorCandidate


@dataclass(frozen=True, slots=True)
class Eligibility:
    eligible: bool
    reason: str
    validity_weight: float


def evaluate_eligibility(candidate: VectorCandidate, *, as_of: datetime) -> Eligibility:
    """Apply current-truth policy without delegating safety to a model."""

    if candidate.status is MemoryStatus.SUPERSEDED:
        return Eligibility(False, "superseded_history_only", 0.0)
    if candidate.status is MemoryStatus.EXPIRED:
        return Eligibility(False, "expired_history_only", 0.0)
    if candidate.status is MemoryStatus.DISPUTED:
        return Eligibility(False, "disputed_cannot_independently_authorize", 0.25)
    if candidate.superseded_by is not None:
        return Eligibility(False, "active_status_conflicts_with_supersession_link", 0.0)
    if candidate.valid_from > as_of:
        return Eligibility(False, "not_yet_valid", 0.0)
    if candidate.valid_until is not None and candidate.valid_until <= as_of:
        return Eligibility(False, "expired_by_time", 0.0)
    return Eligibility(True, "active_current_evidence", 1.0)


@dataclass(frozen=True, slots=True)
class RerankWeights:
    semantic_similarity: float = 0.55
    device_context_match: float = 0.15
    confidence: float = 0.10
    validity: float = 0.10
    successful_outcome: float = 0.10

    def __post_init__(self) -> None:
        total = sum(
            (
                self.semantic_similarity,
                self.device_context_match,
                self.confidence,
                self.validity,
                self.successful_outcome,
            )
        )
        if abs(total - 1.0) > 1e-9:
            raise ValueError("rerank weights must sum to one")
        if self.semantic_similarity <= max(
            self.device_context_match,
            self.confidence,
            self.validity,
            self.successful_outcome,
        ):
            raise ValueError("semantic similarity must remain the primary signal")


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    final_score: float
    device_context_match: float
    successful_outcome_weight: float


def score_candidate(
    candidate: VectorCandidate,
    context: RetrievalContext,
    eligibility: Eligibility,
    *,
    weights: RerankWeights,
) -> ScoreBreakdown:
    semantic = min(1.0, max(0.0, (candidate.semantic_similarity + 1.0) / 2.0))
    device_match = (
        1.0
        if candidate.device_id is not None and candidate.device_id in context.device_ids
        else 0.0
    )
    if candidate.prior_outcome_success is True:
        outcome_weight = 1.0
    elif candidate.prior_outcome_success is None:
        outcome_weight = 0.25
    else:
        outcome_weight = 0.0
    final = (
        weights.semantic_similarity * semantic
        + weights.device_context_match * device_match
        + weights.confidence * candidate.confidence
        + weights.validity * eligibility.validity_weight
        + weights.successful_outcome * outcome_weight
    )
    return ScoreBreakdown(final, device_match, outcome_weight)
