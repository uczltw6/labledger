"""CockroachDB VECTOR persistence and similarity-query repository."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from datetime import datetime
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.app.db.repository import run_with_serialization_retry
from backend.app.db.types import JSONObject
from backend.app.memory.models import (
    EmbeddedMemory,
    EpisodicMemory,
    MemoryStatus,
    ProviderMetadata,
    VectorCandidate,
)


def serialize_vector(values: Iterable[float], *, expected_dimension: int) -> str:
    """Serialize a finite fixed-dimension vector for a parameterized SQL cast."""

    vector_values: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("vector values must be numbers")
        vector_values.append(float(value))
    vector = tuple(vector_values)
    if len(vector) != expected_dimension:
        raise ValueError(
            f"vector dimension mismatch: expected {expected_dimension}, received {len(vector)}"
        )
    if not all(math.isfinite(value) for value in vector):
        raise ValueError("vector values must be finite")
    return json.dumps(vector, separators=(",", ":"))


def _json_object(value: object) -> JSONObject:
    if not isinstance(value, dict):
        raise TypeError("database provenance must be an object")
    return cast(JSONObject, value)


class CockroachVectorMemoryRepository:
    """Store production embeddings and execute cosine search inside CockroachDB."""

    def __init__(self, database_url: str, *, dimension: int) -> None:
        if not database_url:
            raise ValueError("database_url must not be empty")
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self._database_url = database_url
        self._dimension = dimension

    def _vector_cast(self) -> sql.Composed:
        return sql.SQL("%s::VECTOR({})").format(sql.SQL(str(self._dimension)))

    def save_embedded_memories(self, memories: tuple[EmbeddedMemory, ...]) -> None:
        """Upsert the canonical P3 form while preserving P2 source identifiers."""

        if not memories:
            raise ValueError("at least one embedded memory is required")
        for memory in memories:
            metadata = memory.embedding.metadata
            if metadata.test_only:
                raise ValueError("TEST-ONLY embeddings cannot be written to CockroachDB evidence")
            if metadata.dimension != self._dimension:
                raise ValueError("provider dimension does not match repository dimension")

        ordered = sorted(memories, key=lambda item: item.episode.record.superseded_by is not None)
        for memory in ordered:
            self._save_one(memory)

    def has_matching_embeddings(
        self,
        memories: tuple[EpisodicMemory, ...],
        metadata: ProviderMetadata,
    ) -> bool:
        """Check reusable production vectors without reading vector values."""

        if not memories or metadata.test_only or metadata.dimension != self._dimension:
            return False
        expected = {memory.record.id: memory.record.embedding_text for memory in memories}
        with psycopg.connect(self._database_url) as connection:
            rows = connection.execute(
                """
                SELECT id, embedding_text
                FROM public.memories
                WHERE id = ANY(%s)
                  AND embedding IS NOT NULL
                  AND embedding_provider = %s
                  AND embedding_model_id = %s
                  AND embedding_dimension = %s
                  AND vector_dims(embedding) = %s
                """,
                (
                    list(expected),
                    metadata.provider,
                    metadata.model_id,
                    metadata.dimension,
                    metadata.dimension,
                ),
            ).fetchall()
        actual = {cast(UUID, memory_id): str(text) for memory_id, text in rows}
        return actual == expected

    def _save_one(self, memory: EmbeddedMemory) -> None:
        record = memory.episode.record
        vector = serialize_vector(
            memory.embedding.vector,
            expected_dimension=self._dimension,
        )

        def operation() -> None:
            with (
                psycopg.connect(self._database_url, autocommit=True) as connection,
                connection.transaction(),
            ):
                statement = sql.SQL(
                    """
                    INSERT INTO public.memories (
                        id, lab_id, experiment_run_id, device_id, memory_type,
                        title, content, embedding_text, embedding, embedding_provider,
                        embedding_model_id, embedding_dimension, status, confidence,
                        valid_from, valid_until, superseded_by, source_observation_id,
                        source_action_id, source_outcome_id, provenance, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, {}, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        title = excluded.title,
                        content = excluded.content,
                        embedding_text = excluded.embedding_text,
                        embedding = excluded.embedding,
                        embedding_provider = excluded.embedding_provider,
                        embedding_model_id = excluded.embedding_model_id,
                        embedding_dimension = excluded.embedding_dimension,
                        status = excluded.status,
                        confidence = excluded.confidence,
                        valid_from = excluded.valid_from,
                        valid_until = excluded.valid_until,
                        superseded_by = excluded.superseded_by,
                        provenance = excluded.provenance
                    """
                ).format(self._vector_cast())
                connection.execute(
                    statement,
                    (
                        record.id,
                        record.lab_id,
                        record.experiment_run_id,
                        record.device_id,
                        record.memory_type,
                        record.title,
                        record.content,
                        record.embedding_text,
                        vector,
                        memory.embedding.metadata.provider,
                        memory.embedding.metadata.model_id,
                        memory.embedding.metadata.dimension,
                        record.status,
                        record.confidence,
                        record.valid_from,
                        record.valid_until,
                        record.superseded_by,
                        record.source_observation_id,
                        record.source_action_id,
                        record.source_outcome_id,
                        Jsonb(record.provenance),
                        record.created_at,
                    ),
                )

        run_with_serialization_retry(operation)

    def search(
        self,
        *,
        lab_id: UUID,
        query_vector: tuple[float, ...],
        limit: int,
        memory_types: tuple[str, ...],
    ) -> tuple[VectorCandidate, ...]:
        if limit < 1:
            raise ValueError("search limit must be positive")
        vector = serialize_vector(query_vector, expected_dimension=self._dimension)
        type_clause = sql.SQL("")
        parameters: list[object] = [vector, vector, lab_id]
        if memory_types:
            type_clause = sql.SQL(" AND m.memory_type = ANY(%s)")
            parameters.append(list(memory_types))
        parameters.append(limit)
        statement = sql.SQL(
            """
            SELECT
                m.id, m.title, m.memory_type, m.content, m.embedding_text,
                m.status, m.confidence, m.valid_from, m.valid_until,
                m.superseded_by, m.lab_id, m.experiment_run_id, m.device_id,
                m.source_observation_id, m.source_action_id, m.source_outcome_id,
                m.provenance, a.action_type AS prior_action,
                o.success AS prior_outcome_success,
                o.summary AS prior_outcome_summary,
                o.error_code AS prior_outcome_error_code,
                m.embedding <=> {} AS cosine_distance,
                1.0 - (m.embedding <=> {}) AS semantic_similarity
            FROM public.memories AS m
            LEFT JOIN public.actions AS a ON a.id = m.source_action_id
            LEFT JOIN public.outcomes AS o ON o.id = m.source_outcome_id
            WHERE m.lab_id = %s AND m.embedding IS NOT NULL{}
            ORDER BY m.embedding <=> {}
            LIMIT %s
            """
        ).format(
            self._vector_cast(),
            self._vector_cast(),
            type_clause,
            self._vector_cast(),
        )
        parameters.insert(-1, vector)
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            rows = connection.execute(statement, parameters).fetchall()
        return tuple(self._candidate(row) for row in rows)

    @staticmethod
    def _candidate(row: dict[str, Any]) -> VectorCandidate:
        provenance = _json_object(row["provenance"])
        return VectorCandidate(
            memory_id=cast(UUID, row["id"]),
            title=str(row["title"]),
            memory_type=str(row["memory_type"]),
            content=str(row["content"]),
            embedding_text=str(row["embedding_text"]),
            status=MemoryStatus(str(row["status"])),
            confidence=float(row["confidence"]),
            valid_from=cast(datetime, row["valid_from"]),
            valid_until=cast(datetime | None, row["valid_until"]),
            superseded_by=cast(UUID | None, row["superseded_by"]),
            lab_id=cast(UUID, row["lab_id"]),
            experiment_run_id=cast(UUID | None, row["experiment_run_id"]),
            device_id=cast(UUID | None, row["device_id"]),
            source_observation_id=cast(UUID | None, row["source_observation_id"]),
            source_action_id=cast(UUID | None, row["source_action_id"]),
            source_outcome_id=cast(UUID | None, row["source_outcome_id"]),
            provenance=provenance,
            prior_action=None if row["prior_action"] is None else str(row["prior_action"]),
            prior_outcome_success=cast(bool | None, row["prior_outcome_success"]),
            prior_outcome_summary=(
                None if row["prior_outcome_summary"] is None else str(row["prior_outcome_summary"])
            ),
            prior_outcome_error_code=(
                None
                if row["prior_outcome_error_code"] is None
                else str(row["prior_outcome_error_code"])
            ),
            cosine_distance=float(row["cosine_distance"]),
            semantic_similarity=float(row["semantic_similarity"]),
        )

    def query_plan_mentions_vector_index(
        self,
        *,
        lab_id: UUID,
        query_vector: tuple[float, ...],
        index_name: str,
    ) -> bool:
        """Return only non-sensitive planner evidence, never the plan/vector itself."""

        vector = serialize_vector(query_vector, expected_dimension=self._dimension)
        statement = sql.SQL(
            """
            EXPLAIN SELECT id
            FROM public.memories
            WHERE lab_id = %s AND embedding IS NOT NULL
            ORDER BY embedding <=> {}
            LIMIT 3
            """
        ).format(self._vector_cast())
        with psycopg.connect(self._database_url) as connection:
            rows = connection.execute(statement, (lab_id, vector)).fetchall()
        plan = "\n".join(str(row[0]) for row in rows)
        return index_name in plan
