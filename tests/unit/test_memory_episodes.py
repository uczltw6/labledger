from backend.app.db.mapping import build_hero_seed
from backend.app.memory.episodes import build_hero_episodes, canonical_embedding_text


def test_hero_memories_are_canonical_observation_action_outcome_lessons() -> None:
    episodes = build_hero_episodes(build_hero_seed())

    assert len(episodes) == 4
    intervention = next(
        memory for memory in episodes if memory.record.memory_type == "intervention_result"
    )
    text = intervention.record.embedding_text
    assert text == canonical_embedding_text(intervention)
    assert "temperature elevated" in text
    assert "calibration_A; outcome: failed" in text
    assert "reduce_drive_10_percent; outcome: succeeded" in text
    assert "noise decreased and signal quality recovered" in text
    assert "2026-" not in text


def test_canonical_text_is_byte_stable_for_identical_structured_seed() -> None:
    first = [memory.record.embedding_text for memory in build_hero_episodes(build_hero_seed())]
    second = [memory.record.embedding_text for memory in build_hero_episodes(build_hero_seed())]

    assert first == second


def test_episodic_memory_preserves_p2_source_and_provenance_links() -> None:
    seed = build_hero_seed()
    episodes = build_hero_episodes(seed)

    for episode in episodes:
        original = next(memory for memory in seed.memories if memory.id == episode.record.id)
        assert episode.record.experiment_run_id == original.experiment_run_id
        assert episode.record.source_observation_id == original.source_observation_id
        assert episode.record.source_action_id == original.source_action_id
        assert episode.record.source_outcome_id == original.source_outcome_id
        assert episode.record.provenance["synthetic"] is True
        assert episode.record.provenance["episode_schema"] == (
            "observation-action-outcome-lesson-v1"
        )


def test_calibration_memory_keeps_real_supersession_and_current_values() -> None:
    episodes = build_hero_episodes(build_hero_seed())
    calibration = {
        memory.record.status: memory
        for memory in episodes
        if memory.record.memory_type == "calibration_fact"
    }

    superseded = calibration["superseded"]
    active = calibration["active"]
    assert "gain 4.2" in superseded.record.embedding_text
    assert superseded.record.superseded_by == active.record.id
    assert "gain 3.8" in active.record.embedding_text
    assert active.record.superseded_by is None
