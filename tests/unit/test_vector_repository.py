from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.memory.models import MemoryStatus
from backend.app.memory.repository import CockroachVectorMemoryRepository, serialize_vector

ROOT = Path(__file__).resolve().parents[2]


def test_vector_parameter_serialization_is_compact_and_dimension_checked() -> None:
    assert serialize_vector((0.1, -0.2, 0.3), expected_dimension=3) == "[0.1,-0.2,0.3]"
    with pytest.raises(ValueError, match="dimension mismatch"):
        serialize_vector((0.1,), expected_dimension=3)
    with pytest.raises(ValueError, match="finite"):
        serialize_vector((0.1, float("nan"), 0.3), expected_dimension=3)


def test_retrieval_row_mapping_preserves_source_action_and_outcome() -> None:
    memory_id = uuid4()
    run_id = uuid4()
    device_id = uuid4()
    action_id = uuid4()
    outcome_id = uuid4()
    now = datetime(2026, 8, 9, tzinfo=UTC)

    candidate = CockroachVectorMemoryRepository._candidate(
        {
            "id": memory_id,
            "title": "Drive reduction restored signal quality",
            "memory_type": "intervention_result",
            "content": "content",
            "embedding_text": "embedding text",
            "status": "active",
            "confidence": 1.0,
            "valid_from": now,
            "valid_until": None,
            "superseded_by": None,
            "lab_id": uuid4(),
            "experiment_run_id": run_id,
            "device_id": device_id,
            "source_observation_id": uuid4(),
            "source_action_id": action_id,
            "source_outcome_id": outcome_id,
            "provenance": {"synthetic": True},
            "prior_action": "reduce_drive_10_percent",
            "prior_outcome_success": True,
            "prior_outcome_summary": "action succeeded",
            "prior_outcome_error_code": None,
            "cosine_distance": 0.1,
            "semantic_similarity": 0.9,
        }
    )

    assert candidate.memory_id == memory_id
    assert candidate.experiment_run_id == run_id
    assert candidate.device_id == device_id
    assert candidate.source_action_id == action_id
    assert candidate.source_outcome_id == outcome_id
    assert candidate.prior_action == "reduce_drive_10_percent"
    assert candidate.prior_outcome_success is True
    assert candidate.status is MemoryStatus.ACTIVE


def test_p2_action_schema_already_exposes_unfabricated_influence_ids() -> None:
    sql = (ROOT / "migrations" / "001_init.sql").read_text(encoding="utf-8")

    assert "memory_ids UUID[] NOT NULL" in sql
    assert "DEFAULT ARRAY[]::UUID[]" in sql
