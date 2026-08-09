from pathlib import Path

import pytest

from backend.app.settings import EmbeddingSettings, SettingsError, load_environment
from scripts.verify_p3 import LiveP3Evidence, run_live_verification

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def live_p3() -> LiveP3Evidence:
    values = load_environment(ROOT)
    if not values.get("COCKROACH_DATABASE_URL"):
        pytest.skip("COCKROACH_DATABASE_URL is absent; live P3 evidence is unavailable")
    try:
        EmbeddingSettings.from_mapping(values)
    except SettingsError as error:
        pytest.skip(f"production embedding configuration is absent: {error}")
    return run_live_verification(write_evidence=False)


def test_live_vector_schema_index_and_dimensions(live_p3: LiveP3Evidence) -> None:
    assert live_p3.schema.column_type == f"vector({live_p3.settings.dimension})"
    assert live_p3.schema.index_definition_present is True
    assert live_p3.schema.embedded_row_count >= 4
    assert live_p3.schema.dimension_match_count == live_p3.schema.embedded_row_count
    assert live_p3.schema.metadata_match_count == live_p3.schema.embedded_row_count


def test_live_expected_intervention_recall_at_three(live_p3: LiveP3Evidence) -> None:
    top_three = {str(item.candidate.memory_id) for item in live_p3.relevant_retrieval.ranked}
    assert live_p3.expected_intervention_id in top_three


def test_live_intervention_keeps_structured_source_links(live_p3: LiveP3Evidence) -> None:
    item = next(
        item
        for item in live_p3.relevant_retrieval.ranked
        if str(item.candidate.memory_id) == live_p3.expected_intervention_id
    )
    assert item.candidate.source_observation_id is not None
    assert item.candidate.source_action_id is not None
    assert item.candidate.source_outcome_id is not None
    assert item.candidate.prior_action == "reduce_drive_10_percent"
    assert item.candidate.prior_outcome_success is True


def test_live_superseded_calibration_visible_but_ineligible(
    live_p3: LiveP3Evidence,
) -> None:
    by_status = {item.candidate.status.value: item for item in live_p3.calibration_retrieval.ranked}
    assert by_status["superseded"].eligible_for_action is False
    assert by_status["active"].eligible_for_action is True
    assert all(
        item.candidate.status.value != "superseded"
        for item in live_p3.calibration_retrieval.eligible_evidence
    )
