"""Verify P3 semantic memory against Bedrock and live CockroachDB."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid5

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.mapping import (  # noqa: E402
    DEFAULT_SEED_LAB_ID,
    build_hero_seed,
)
from backend.app.db.migrations import verify_p2_schema  # noqa: E402
from backend.app.db.psycopg_repository import (  # noqa: E402
    PsycopgStructuredMemoryRepository,
)
from backend.app.memory.embedding import (  # noqa: E402
    BedrockTitanEmbeddingProvider,
    EmbeddingError,
    EmbeddingInvocationError,
    EmbeddingProvider,
)
from backend.app.memory.episodes import build_hero_episodes  # noqa: E402
from backend.app.memory.models import (  # noqa: E402
    EmbeddedMemory,
    RetrievalContext,
    RetrievalResult,
)
from backend.app.memory.repository import CockroachVectorMemoryRepository  # noqa: E402
from backend.app.memory.retrieval import MemoryRetrievalService  # noqa: E402
from backend.app.memory.schema import (  # noqa: E402
    P3_VECTOR_INDEX,
    VectorSchemaEvidence,
    apply_p3_migration,
    migration_dimension,
    verify_p3_schema,
)
from backend.app.settings import (  # noqa: E402
    EmbeddingSettings,
    SettingsError,
    load_environment,
)
from scripts.verify_p2 import _preflight_database_url  # noqa: E402

MIGRATION = ROOT / "migrations" / "002_vector_memory.sql"
EVIDENCE_PATH = ROOT / "docs" / "evidence" / "p3-vector-memory.json"


@dataclass(frozen=True, slots=True)
class LiveP3Evidence:
    settings: EmbeddingSettings
    visible_model_ids: tuple[str, ...]
    schema: VectorSchemaEvidence
    relevant_retrieval: RetrievalResult
    calibration_retrieval: RetrievalResult
    expected_intervention_id: str
    vector_index_in_query_plan: bool


def _visible_embedding_models(settings: EmbeddingSettings) -> tuple[str, ...]:
    import boto3  # type: ignore[import-untyped]

    try:
        session = boto3.Session(
            profile_name=settings.aws_profile,
            region_name=settings.aws_region,
        )
        client = session.client("bedrock", region_name=settings.aws_region)
        response = client.list_foundation_models(byOutputModality="EMBEDDING")
    except Exception as error:
        response_data = getattr(error, "response", None)
        code = type(error).__name__
        if isinstance(response_data, dict):
            raw_error = response_data.get("Error")
            if isinstance(raw_error, dict) and isinstance(raw_error.get("Code"), str):
                code = str(raw_error["Code"])
        raise EmbeddingInvocationError(
            f"Bedrock embedding-model visibility check failed ({code})"
        ) from error
    summaries = response.get("modelSummaries")
    if not isinstance(summaries, list):
        raise EmbeddingInvocationError("Bedrock model visibility response is malformed")
    identifiers = sorted(
        str(summary["modelId"])
        for summary in summaries
        if isinstance(summary, dict) and isinstance(summary.get("modelId"), str)
    )
    return tuple(identifiers)


def _embed_episodes(
    provider: EmbeddingProvider,
) -> tuple[EmbeddedMemory, ...]:
    episodes = build_hero_episodes(build_hero_seed())
    return tuple(
        EmbeddedMemory(episode=episode, embedding=provider.embed(episode.record.embedding_text))
        for episode in episodes
    )


def _relevant_context() -> RetrievalContext:
    return RetrievalContext(
        lab_id=DEFAULT_SEED_LAB_ID,
        observation=(
            "The enclosure is running warmer than normal, waveform noise has climbed, and "
            "the measured acquisition quality has deteriorated. Retrieve evidence about "
            "unsuccessful calibration and a safe source-level intervention."
        ),
        device_ids=(
            uuid5(DEFAULT_SEED_LAB_ID, "device:temperature_01"),
            uuid5(DEFAULT_SEED_LAB_ID, "device:scope_01"),
            uuid5(DEFAULT_SEED_LAB_ID, "device:signal_source_01"),
        ),
        device_context=("temperature_01", "scope_01", "signal_source_01"),
        as_of=datetime(2026, 8, 9, tzinfo=UTC),
    )


def _calibration_context() -> RetrievalContext:
    return RetrievalContext(
        lab_id=DEFAULT_SEED_LAB_ID,
        observation=(
            "Which scope gain calibration is current? Compare historical gain 4.2 with the "
            "newer gain 3.8 while retaining superseded evidence."
        ),
        device_ids=(uuid5(DEFAULT_SEED_LAB_ID, "device:scope_01"),),
        device_context=("scope_01",),
        as_of=datetime(2026, 8, 9, tzinfo=UTC),
        memory_types=("calibration_fact",),
    )


def run_live_verification(*, write_evidence: bool) -> LiveP3Evidence:
    values = load_environment(ROOT)
    database_url = values.get("COCKROACH_DATABASE_URL", "").strip()
    if not database_url:
        raise SettingsError("COCKROACH_DATABASE_URL is required for live P3 verification")
    _preflight_database_url(database_url)
    settings = EmbeddingSettings.from_mapping(values)
    if not MIGRATION.is_file():
        raise SettingsError("P3 vector migration is missing")
    if migration_dimension(MIGRATION) != settings.dimension:
        raise SettingsError("P3 migration dimension does not match EMBEDDING_DIM")

    visible_model_ids = _visible_embedding_models(settings)
    if settings.model_id not in visible_model_ids:
        raise EmbeddingInvocationError(
            "configured embedding model is not account-visible in the selected Region"
        )
    provider = BedrockTitanEmbeddingProvider(settings)

    structured_repository = PsycopgStructuredMemoryRepository(database_url)
    structured_repository.save_hero_seed(build_hero_seed())
    apply_p3_migration(database_url, MIGRATION)
    apply_p3_migration(database_url, MIGRATION)
    p2_errors = verify_p2_schema(database_url)
    if p2_errors:
        raise RuntimeError("P3 migration regressed the P2 schema: " + "; ".join(p2_errors))

    vector_repository = CockroachVectorMemoryRepository(
        database_url,
        dimension=settings.dimension,
    )
    episodes = build_hero_episodes(build_hero_seed())
    if not vector_repository.has_matching_embeddings(episodes, provider.metadata):
        vector_repository.save_embedded_memories(_embed_episodes(provider))
    schema_errors, schema_evidence = verify_p3_schema(
        database_url,
        expected_dimension=settings.dimension,
        expected_provider=provider.metadata.provider,
        expected_model_id=settings.model_id,
    )
    if schema_errors:
        raise RuntimeError("; ".join(schema_errors))

    service = MemoryRetrievalService(provider, vector_repository)
    relevant = service.retrieve(_relevant_context(), top_k=3)
    calibration = service.retrieve(_calibration_context(), top_k=3)
    intervention = next(
        memory for memory in episodes if memory.record.memory_type == "intervention_result"
    )
    expected_id = str(intervention.record.id)
    retrieved_ids = {str(item.candidate.memory_id) for item in relevant.ranked}
    if expected_id not in retrieved_ids:
        raise RuntimeError("expected intervention episode was not returned within top-3")
    expected_candidate = next(
        item for item in relevant.ranked if str(item.candidate.memory_id) == expected_id
    )
    if (
        expected_candidate.candidate.prior_action != "reduce_drive_10_percent"
        or expected_candidate.candidate.prior_outcome_success is not True
        or expected_candidate.candidate.source_observation_id is None
        or expected_candidate.candidate.source_action_id is None
        or expected_candidate.candidate.source_outcome_id is None
    ):
        raise RuntimeError("retrieved intervention lost its P2 source/provenance links")

    calibration_by_status = {item.candidate.status.value: item for item in calibration.ranked}
    if "superseded" not in calibration_by_status or "active" not in calibration_by_status:
        raise RuntimeError("calibration retrieval did not expose both historical and active facts")
    superseded = calibration_by_status["superseded"]
    active = calibration_by_status["active"]
    if superseded.eligible_for_action:
        raise RuntimeError("superseded calibration entered current-action evidence")
    if not active.eligible_for_action:
        raise RuntimeError("active calibration was not eligible for current action")
    if any(item.candidate.status.value == "superseded" for item in calibration.eligible_evidence):
        raise RuntimeError("eligible evidence contains a superseded calibration")

    index_in_plan = vector_repository.query_plan_mentions_vector_index(
        lab_id=DEFAULT_SEED_LAB_ID,
        query_vector=(1.0,) + (0.0,) * (settings.dimension - 1),
        index_name=P3_VECTOR_INDEX,
    )
    evidence = LiveP3Evidence(
        settings=settings,
        visible_model_ids=visible_model_ids,
        schema=schema_evidence,
        relevant_retrieval=relevant,
        calibration_retrieval=calibration,
        expected_intervention_id=expected_id,
        vector_index_in_query_plan=index_in_plan,
    )
    if write_evidence:
        _write_evidence(evidence)
    return evidence


def _retrieval_json(result: RetrievalResult) -> dict[str, object]:
    return {
        "query_text": result.query_text,
        "top_k": [
            {
                "memory_id": str(item.candidate.memory_id),
                "title": item.candidate.title,
                "rank": item.final_rank,
                "cosine_distance": round(item.candidate.cosine_distance, 8),
                "semantic_similarity": round(item.candidate.semantic_similarity, 8),
                "final_score": round(item.final_score, 8),
                "status": item.candidate.status.value,
                "eligible_for_action": item.eligible_for_action,
                "eligibility_reason": item.eligibility_reason,
                "source_run": (
                    None
                    if item.candidate.experiment_run_id is None
                    else str(item.candidate.experiment_run_id)
                ),
                "source_observation": (
                    None
                    if item.candidate.source_observation_id is None
                    else str(item.candidate.source_observation_id)
                ),
                "prior_action": item.candidate.prior_action,
                "prior_outcome": {
                    "success": item.candidate.prior_outcome_success,
                    "summary": item.candidate.prior_outcome_summary,
                    "error_code": item.candidate.prior_outcome_error_code,
                },
            }
            for item in result.ranked
        ],
        "eligible_memory_ids": [str(item.candidate.memory_id) for item in result.eligible_evidence],
    }


def _write_evidence(evidence: LiveP3Evidence) -> None:
    payload = {
        "evidence_schema": "labledger-p3-vector-memory-v1",
        "generated_from_live_verifier": True,
        "embedding": {
            "provider": "amazon-bedrock",
            "model_id": evidence.settings.model_id,
            "region": evidence.settings.aws_region,
            "dimension": evidence.settings.dimension,
            "account_model_visibility_verified": True,
        },
        "cockroachdb": {
            "vector_column_type": evidence.schema.column_type,
            "vector_index": evidence.schema.index_name,
            "vector_index_definition_present": evidence.schema.index_definition_present,
            "embedded_rows": evidence.schema.embedded_row_count,
            "dimension_match_rows": evidence.schema.dimension_match_count,
            "provider_metadata_match_rows": evidence.schema.metadata_match_count,
            "live_query_executed_in_cockroachdb": True,
            "query_plan_selected_vector_index": evidence.vector_index_in_query_plan,
            "dataset_note": "small deterministic four-memory synthetic hero dataset",
        },
        "hero_retrieval": _retrieval_json(evidence.relevant_retrieval),
        "calibration_validity": _retrieval_json(evidence.calibration_retrieval),
    }
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _print_summary(evidence: LiveP3Evidence) -> None:
    print(
        "[PASS] Production embedding: "
        f"provider=amazon-bedrock model={evidence.settings.model_id} "
        f"region={evidence.settings.aws_region} dimension={evidence.settings.dimension}"
    )
    print("[PASS] Selected embedding model is account-visible in the configured Region")
    print(
        "[PASS] CockroachDB VECTOR schema: "
        f"column={evidence.schema.column_type} index={evidence.schema.index_name} "
        f"embedded_rows={evidence.schema.embedded_row_count}"
    )
    for item in evidence.relevant_retrieval.ranked:
        print(
            f"[TOP-{item.final_rank}] {item.candidate.title}; "
            f"similarity={item.candidate.semantic_similarity:.6f}; "
            f"status={item.candidate.status.value}; eligible={item.eligible_for_action}"
        )
    print("[PASS] Expected intervention episode is within live CockroachDB top-3")
    print("[PASS] Superseded calibration is visible but excluded from eligible evidence")
    print("P3 Gate: PASS")


def _local_check() -> None:
    from backend.app.memory.embedding import DeterministicTestEmbeddingProvider

    episodes = build_hero_episodes(build_hero_seed())
    provider = DeterministicTestEmbeddingProvider(32)
    embedded = [provider.embed(episode.record.embedding_text) for episode in episodes]
    if len(episodes) != 4 or any(len(item.vector) != 32 for item in embedded):
        raise RuntimeError("local P3 episode/provider contract failed")
    print("[PASS] P3 canonical episodes and TEST-ONLY provider contract")
    print("[INFO] TEST-ONLY embeddings do not satisfy Gate P3")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", action="store_true", help="run credential-free contracts only")
    parser.add_argument(
        "--no-write-evidence",
        action="store_true",
        help="run the live gate without replacing the evidence artifact",
    )
    arguments = parser.parse_args(argv)
    try:
        if arguments.local:
            _local_check()
        else:
            evidence = run_live_verification(write_evidence=not arguments.no_write_evidence)
            _print_summary(evidence)
    except Exception as error:
        safe_message = (
            str(error)
            if isinstance(error, (EmbeddingError, SettingsError, RuntimeError, ValueError))
            else "live P3 operation failed; sensitive connection details suppressed"
        )
        print(
            json.dumps(
                {
                    "error_type": type(error).__name__,
                    "message": safe_message,
                    "p3_gate": "NOT_PASS",
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
