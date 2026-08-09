from datetime import UTC, datetime
from uuid import UUID, uuid4

from backend.app.memory.embedding import DeterministicTestEmbeddingProvider
from backend.app.memory.models import MemoryStatus, RetrievalContext, VectorCandidate
from backend.app.memory.retrieval import MemoryRetrievalService, canonical_retrieval_text


class _Repository:
    def __init__(self, candidates: tuple[VectorCandidate, ...]) -> None:
        self.candidates = candidates
        self.received_limit = 0

    def search(
        self,
        *,
        lab_id: UUID,
        query_vector: tuple[float, ...],
        limit: int,
        memory_types: tuple[str, ...],
    ) -> tuple[VectorCandidate, ...]:
        del lab_id, query_vector, memory_types
        self.received_limit = limit
        return self.candidates[:limit]


def _candidate(
    *,
    title: str,
    similarity: float,
    status: MemoryStatus,
    device_id: UUID,
    success: bool | None,
) -> VectorCandidate:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    return VectorCandidate(
        memory_id=uuid4(),
        title=title,
        memory_type="intervention_result",
        content=title,
        embedding_text=title,
        status=status,
        confidence=1.0,
        valid_from=now,
        valid_until=None,
        superseded_by=None,
        lab_id=uuid4(),
        experiment_run_id=uuid4(),
        device_id=device_id,
        source_observation_id=uuid4(),
        source_action_id=uuid4(),
        source_outcome_id=uuid4(),
        provenance={"synthetic": True},
        prior_action="reduce_drive_10_percent",
        prior_outcome_success=success,
        prior_outcome_summary="action succeeded" if success else "action failed",
        prior_outcome_error_code=None,
        cosine_distance=1.0 - similarity,
        semantic_similarity=similarity,
    )


def test_retrieval_query_is_deterministic_and_not_stored_memory_copy() -> None:
    context = RetrievalContext(
        lab_id=uuid4(),
        observation=(
            "The enclosure is warmer while waveform noise rose and measurement quality fell."
        ),
        device_ids=(),
        device_context=("temperature_01", "scope_01"),
        as_of=datetime(2026, 8, 9, tzinfo=UTC),
    )

    text = canonical_retrieval_text(context)

    assert text == canonical_retrieval_text(context)
    assert "calibration_A FAILED" not in text
    assert "warmer" in text


def test_retrieval_reranks_top_k_and_separates_historical_from_eligible() -> None:
    device_id = uuid4()
    candidates = (
        _candidate(
            title="prior successful intervention",
            similarity=0.85,
            status=MemoryStatus.ACTIVE,
            device_id=device_id,
            success=True,
        ),
        _candidate(
            title="superseded calibration",
            similarity=0.95,
            status=MemoryStatus.SUPERSEDED,
            device_id=device_id,
            success=None,
        ),
        _candidate(
            title="weak unrelated evidence",
            similarity=0.30,
            status=MemoryStatus.DISPUTED,
            device_id=uuid4(),
            success=False,
        ),
    )
    repository = _Repository(candidates)
    service = MemoryRetrievalService(
        DeterministicTestEmbeddingProvider(8),
        repository,
        candidate_limit=3,
    )
    context = RetrievalContext(
        lab_id=uuid4(),
        observation="warmer enclosure, increased noise, degraded quality",
        device_ids=(device_id,),
        device_context=("scope_01",),
        as_of=datetime(2026, 8, 9, tzinfo=UTC),
    )

    result = service.retrieve(context, top_k=3)

    assert [item.final_rank for item in result.ranked] == [1, 2, 3]
    assert result.ranked[0].candidate.title == "prior successful intervention"
    historical = next(
        item for item in result.ranked if item.candidate.title == "superseded calibration"
    )
    assert historical.eligible_for_action is False
    assert historical.eligibility_reason == "superseded_history_only"
    assert [item.candidate.title for item in result.eligible_evidence] == [
        "prior successful intervention"
    ]
    assert repository.received_limit == 3
    assert result.provider.test_only is True
