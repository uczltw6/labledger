"""Typed P3 semantic-memory and retrieval evidence models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from backend.app.db.types import JSONObject, MemoryRecord


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    DISPUTED = "disputed"


@dataclass(frozen=True, slots=True)
class ActionEvidence:
    action_type: str
    outcome: str
    detail: str


@dataclass(frozen=True, slots=True)
class EpisodeSections:
    observation: str
    actions: tuple[ActionEvidence, ...]
    outcome: str
    lesson: str


@dataclass(frozen=True, slots=True)
class EpisodicMemory:
    """One semantic episode linked back to P2 structured evidence."""

    record: MemoryRecord
    device_context: tuple[str, ...]
    sections: EpisodeSections


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    provider: str
    model_id: str
    dimension: int
    region: str | None
    test_only: bool


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    vector: tuple[float, ...]
    metadata: ProviderMetadata
    input_token_count: int | None


@dataclass(frozen=True, slots=True)
class EmbeddedMemory:
    episode: EpisodicMemory
    embedding: EmbeddingResult


@dataclass(frozen=True, slots=True)
class RetrievalContext:
    lab_id: UUID
    observation: str
    device_ids: tuple[UUID, ...]
    device_context: tuple[str, ...]
    as_of: datetime
    memory_types: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VectorCandidate:
    memory_id: UUID
    title: str
    memory_type: str
    content: str
    embedding_text: str
    status: MemoryStatus
    confidence: float
    valid_from: datetime
    valid_until: datetime | None
    superseded_by: UUID | None
    lab_id: UUID
    experiment_run_id: UUID | None
    device_id: UUID | None
    source_observation_id: UUID | None
    source_action_id: UUID | None
    source_outcome_id: UUID | None
    provenance: JSONObject
    prior_action: str | None
    prior_outcome_success: bool | None
    prior_outcome_summary: str | None
    prior_outcome_error_code: str | None
    cosine_distance: float
    semantic_similarity: float


@dataclass(frozen=True, slots=True)
class RetrievedMemory:
    candidate: VectorCandidate
    final_score: float
    final_rank: int
    device_context_match: float
    validity_weight: float
    successful_outcome_weight: float
    eligible_for_action: bool
    eligibility_reason: str
    retrieval_reason: str


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    query_text: str
    provider: ProviderMetadata
    ranked: tuple[RetrievedMemory, ...]
    eligible_evidence: tuple[RetrievedMemory, ...]
