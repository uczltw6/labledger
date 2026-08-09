"""Construct canonical semantic episodes from verified P2 structured evidence."""

from __future__ import annotations

from dataclasses import replace

from backend.app.db.types import HeroSeed, MemoryRecord, TraceRows
from backend.app.memory.models import (
    ActionEvidence,
    EpisodeSections,
    EpisodicMemory,
)


def _clean(value: str) -> str:
    return " ".join(value.strip().split())


def canonical_embedding_text(memory: EpisodicMemory) -> str:
    """Render stable evidence-first text without timestamps or LLM prose."""

    lines = [
        f"memory_type: {_clean(memory.record.memory_type)}",
        f"device_context: {', '.join(_clean(item) for item in memory.device_context)}",
        f"observation: {_clean(memory.sections.observation)}",
    ]
    for action in memory.sections.actions:
        lines.append(
            "action: "
            f"{_clean(action.action_type)}; outcome: {_clean(action.outcome)}; "
            f"detail: {_clean(action.detail)}"
        )
    lines.extend(
        (
            f"resulting_state: {_clean(memory.sections.outcome)}",
            f"lesson: {_clean(memory.sections.lesson)}",
        )
    )
    return "\n".join(lines)


def _memory(seed: HeroSeed, memory_type: str) -> MemoryRecord:
    return next(row for row in seed.memories if row.memory_type == memory_type)


def _trace(seed: HeroSeed, scenario_fragment: str) -> TraceRows:
    return next(row for row in seed.traces if scenario_fragment in row.run.name)


def _with_canonical_text(memory: EpisodicMemory) -> EpisodicMemory:
    canonical = canonical_embedding_text(memory)
    provenance = dict(memory.record.provenance)
    provenance["episode_schema"] = "observation-action-outcome-lesson-v1"
    return replace(
        memory,
        record=replace(memory.record, embedding_text=canonical, provenance=provenance),
    )


def build_hero_episodes(seed: HeroSeed) -> tuple[EpisodicMemory, ...]:
    """Derive the four P3 hero memories without shadowing P2 source truth."""

    connection_trace = _trace(seed, "scenario-a")
    intervention_trace = _trace(seed, "scenario-b")

    failed_connect = next(
        action
        for action in connection_trace.actions
        if action.action_type == "connect" and action.status == "failed"
    )
    successful_connect = next(
        action
        for action in connection_trace.actions
        if action.action_type == "connect" and action.status == "succeeded"
    )
    failed_connect_outcome = next(
        outcome for outcome in connection_trace.outcomes if outcome.action_id == failed_connect.id
    )
    successful_connect_outcome = next(
        outcome
        for outcome in connection_trace.outcomes
        if outcome.action_id == successful_connect.id
    )
    connection = EpisodicMemory(
        record=_memory(seed, "connection_recovery"),
        device_context=("scope_01",),
        sections=EpisodeSections(
            observation="scope connection failed because the cached resource was stale",
            actions=(
                ActionEvidence(
                    failed_connect.action_type,
                    "failed",
                    f"cached resource reconnect returned {failed_connect_outcome.error_code}",
                ),
                ActionEvidence(
                    "rediscover_resources -> connect -> identify",
                    "succeeded",
                    "discovered candidate was connected and its scope identity was verified",
                ),
            ),
            outcome=(
                "scope connection restored"
                if successful_connect_outcome.success
                else "scope connection remained unavailable"
            ),
            lesson=(
                "for a similar stale-resource failure, validate rediscovery and identity "
                "instead of blindly repeating the stale connection attempt"
            ),
        ),
    )

    failed_calibration = next(
        action for action in intervention_trace.actions if action.action_type == "calibration_A"
    )
    reduction = next(
        action
        for action in intervention_trace.actions
        if action.action_type == "reduce_drive_10_percent"
    )
    failed_calibration_outcome = next(
        outcome
        for outcome in intervention_trace.outcomes
        if outcome.action_id == failed_calibration.id
    )
    reduction_outcome = next(
        outcome for outcome in intervention_trace.outcomes if outcome.action_id == reduction.id
    )
    intervention = EpisodicMemory(
        record=_memory(seed, "intervention_result"),
        device_context=("temperature_01", "scope_01", "signal_source_01"),
        sections=EpisodeSections(
            observation=(
                "temperature elevated; acquisition noise increased; measured signal quality "
                "deteriorated"
            ),
            actions=(
                ActionEvidence(
                    failed_calibration.action_type,
                    "failed",
                    f"calibration attempt returned {failed_calibration_outcome.error_code}",
                ),
                ActionEvidence(
                    reduction.action_type,
                    "succeeded" if reduction_outcome.success else "failed",
                    "drive amplitude reduced by ten percent within the safe envelope",
                ),
            ),
            outcome=(
                "noise decreased and signal quality recovered"
                if reduction_outcome.success
                else "signal quality did not recover"
            ),
            lesson=(
                "for a similar verified anomaly, prior successful drive reduction is stronger "
                "historical evidence than repeating failed calibration_A"
            ),
        ),
    )

    calibration_by_version = {row.version: row for row in seed.calibrations}
    calibration_memories = {
        row.title.rsplit(" ", 1)[-1]: row
        for row in seed.memories
        if row.memory_type == "calibration_fact"
    }
    calibration_v1 = calibration_by_version["v1"]
    calibration_v2 = calibration_by_version["v2"]
    memory_v1 = calibration_memories["v1"]
    memory_v2 = calibration_memories["v2"]
    historical = EpisodicMemory(
        record=memory_v1,
        device_context=("scope_01",),
        sections=EpisodeSections(
            observation="scope calibration v1 recorded gain 4.2",
            actions=(
                ActionEvidence(
                    "select calibration v1",
                    "historical",
                    "no P3 action executed",
                ),
            ),
            outcome="calibration v1 is superseded by calibration v2",
            lesson="retain gain 4.2 as history but never use it as current-action truth",
        ),
    )
    current = EpisodicMemory(
        record=memory_v2,
        device_context=("scope_01",),
        sections=EpisodeSections(
            observation="scope calibration v2 recorded gain 3.8",
            actions=(ActionEvidence("select calibration v2", "current", "no P3 action executed"),),
            outcome="calibration v2 is active and has no superseding calibration",
            lesson="gain 3.8 is the currently valid scope calibration evidence",
        ),
    )

    if memory_v1.superseded_by != memory_v2.id:
        raise ValueError("P2 calibration memory supersession is inconsistent")
    if calibration_v1.superseded_by != calibration_v2.id:
        raise ValueError("P2 calibration row supersession is inconsistent")
    return tuple(
        _with_canonical_text(memory) for memory in (connection, intervention, historical, current)
    )
