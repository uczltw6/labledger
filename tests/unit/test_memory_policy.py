from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.app.memory.models import MemoryStatus, RetrievalContext, VectorCandidate
from backend.app.memory.policy import RerankWeights, evaluate_eligibility, score_candidate

NOW = datetime(2026, 8, 9, tzinfo=UTC)


def _candidate(status: MemoryStatus = MemoryStatus.ACTIVE) -> VectorCandidate:
    return VectorCandidate(
        memory_id=uuid4(),
        title="memory",
        memory_type="calibration_fact",
        content="content",
        embedding_text="embedding text",
        status=status,
        confidence=0.9,
        valid_from=NOW - timedelta(days=1),
        valid_until=None,
        superseded_by=None,
        lab_id=uuid4(),
        experiment_run_id=None,
        device_id=uuid4(),
        source_observation_id=None,
        source_action_id=None,
        source_outcome_id=None,
        provenance={"synthetic": True},
        prior_action=None,
        prior_outcome_success=None,
        prior_outcome_summary=None,
        prior_outcome_error_code=None,
        cosine_distance=0.1,
        semantic_similarity=0.9,
    )


@pytest.mark.parametrize(
    ("status", "eligible", "reason"),
    [
        (MemoryStatus.ACTIVE, True, "active_current_evidence"),
        (MemoryStatus.SUPERSEDED, False, "superseded_history_only"),
        (MemoryStatus.EXPIRED, False, "expired_history_only"),
        (MemoryStatus.DISPUTED, False, "disputed_cannot_independently_authorize"),
    ],
)
def test_validity_policy_is_deterministic(
    status: MemoryStatus,
    eligible: bool,
    reason: str,
) -> None:
    result = evaluate_eligibility(_candidate(status), as_of=NOW)

    assert result.eligible is eligible
    assert result.reason == reason


def test_active_memory_outside_time_window_is_ineligible() -> None:
    expired = replace(_candidate(), valid_until=NOW)
    future = replace(_candidate(), valid_from=NOW + timedelta(seconds=1))

    assert evaluate_eligibility(expired, as_of=NOW).reason == "expired_by_time"
    assert evaluate_eligibility(future, as_of=NOW).reason == "not_yet_valid"


def test_active_status_with_supersession_link_fails_closed() -> None:
    inconsistent = replace(_candidate(), superseded_by=uuid4())

    result = evaluate_eligibility(inconsistent, as_of=NOW)

    assert result.eligible is False
    assert result.reason == "active_status_conflicts_with_supersession_link"


def test_superseded_status_remains_the_primary_historical_reason() -> None:
    historical = replace(
        _candidate(MemoryStatus.SUPERSEDED),
        valid_until=NOW - timedelta(seconds=1),
    )

    assert evaluate_eligibility(historical, as_of=NOW).reason == "superseded_history_only"


def test_reranker_keeps_semantics_primary_and_rewards_context_and_success() -> None:
    candidate = replace(_candidate(), prior_outcome_success=True)
    context = RetrievalContext(
        lab_id=candidate.lab_id,
        observation="current anomaly",
        device_ids=(candidate.device_id,),
        device_context=("scope_01",),
        as_of=NOW,
    )
    eligibility = evaluate_eligibility(candidate, as_of=NOW)

    score = score_candidate(candidate, context, eligibility, weights=RerankWeights())

    assert score.device_context_match == 1.0
    assert score.successful_outcome_weight == 1.0
    assert 0.0 < score.final_score <= 1.0


def test_rerank_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="sum to one"):
        RerankWeights(semantic_similarity=0.50)
