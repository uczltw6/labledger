"""Explicit semantic retrieval -> validity -> deterministic reranking pipeline."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from backend.app.memory.embedding import EmbeddingProvider
from backend.app.memory.models import (
    RetrievalContext,
    RetrievalResult,
    RetrievedMemory,
    VectorCandidate,
)
from backend.app.memory.policy import RerankWeights, evaluate_eligibility, score_candidate


class VectorSearchRepository(Protocol):
    def search(
        self,
        *,
        lab_id: UUID,
        query_vector: tuple[float, ...],
        limit: int,
        memory_types: tuple[str, ...],
    ) -> tuple[VectorCandidate, ...]: ...


def canonical_retrieval_text(context: RetrievalContext) -> str:
    """Build deterministic query text from current measured context."""

    devices = ", ".join(context.device_context) if context.device_context else "unspecified"
    return (
        f"device_context: {devices}\n"
        f"current_observation: {' '.join(context.observation.strip().split())}\n"
        "retrieval_goal: find prior observation, action, measured outcome, and lesson"
    )


class MemoryRetrievalService:
    def __init__(
        self,
        provider: EmbeddingProvider,
        repository: VectorSearchRepository,
        *,
        weights: RerankWeights | None = None,
        candidate_limit: int = 12,
    ) -> None:
        if candidate_limit < 1:
            raise ValueError("candidate_limit must be positive")
        self._provider = provider
        self._repository = repository
        self._weights = RerankWeights() if weights is None else weights
        self._candidate_limit = candidate_limit

    def retrieve(self, context: RetrievalContext, *, top_k: int = 3) -> RetrievalResult:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        query_text = canonical_retrieval_text(context)
        embedded = self._provider.embed(query_text)
        candidates = self._repository.search(
            lab_id=context.lab_id,
            query_vector=embedded.vector,
            limit=max(top_k, self._candidate_limit),
            memory_types=context.memory_types,
        )
        scored: list[tuple[VectorCandidate, float, float, float, bool, str]] = []
        for candidate in candidates:
            eligibility = evaluate_eligibility(candidate, as_of=context.as_of)
            breakdown = score_candidate(
                candidate,
                context,
                eligibility,
                weights=self._weights,
            )
            scored.append(
                (
                    candidate,
                    breakdown.final_score,
                    breakdown.device_context_match,
                    eligibility.validity_weight,
                    eligibility.eligible,
                    eligibility.reason,
                )
            )
        scored.sort(
            key=lambda item: (
                -item[1],
                -item[0].semantic_similarity,
                str(item[0].memory_id),
            )
        )
        ranked = tuple(
            RetrievedMemory(
                candidate=candidate,
                final_score=final_score,
                final_rank=rank,
                device_context_match=device_match,
                validity_weight=validity_weight,
                successful_outcome_weight=(
                    1.0
                    if candidate.prior_outcome_success is True
                    else (0.25 if candidate.prior_outcome_success is None else 0.0)
                ),
                eligible_for_action=eligible,
                eligibility_reason=reason,
                retrieval_reason=(
                    f"semantic_similarity={candidate.semantic_similarity:.6f}; "
                    f"device_match={device_match:.1f}; status={candidate.status.value}"
                ),
            )
            for rank, (
                candidate,
                final_score,
                device_match,
                validity_weight,
                eligible,
                reason,
            ) in enumerate(scored[:top_k], start=1)
        )
        return RetrievalResult(
            query_text=query_text,
            provider=embedded.metadata,
            ranked=ranked,
            eligible_evidence=tuple(item for item in ranked if item.eligible_for_action),
        )
