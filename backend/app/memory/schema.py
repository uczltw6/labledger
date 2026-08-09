"""P3 vector migration and live schema evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import psycopg

from backend.app.db.migrations import apply_migration

P3_VECTOR_INDEX = "ix_memories_embedding_cosine"


@dataclass(frozen=True, slots=True)
class VectorSchemaEvidence:
    column_type: str
    index_name: str
    index_definition_present: bool
    embedded_row_count: int
    dimension_match_count: int
    metadata_match_count: int


def apply_p3_migration(database_url: str, path: Path) -> None:
    apply_migration(database_url, path)


def migration_dimension(path: Path) -> int:
    sql_text = path.read_text(encoding="utf-8")
    matches = {int(value) for value in re.findall(r"VECTOR\((\d+)\)", sql_text, re.IGNORECASE)}
    if len(matches) != 1:
        raise ValueError("P3 migration must contain exactly one consistent VECTOR dimension")
    return matches.pop()


def verify_p3_schema(
    database_url: str,
    *,
    expected_dimension: int,
    expected_provider: str,
    expected_model_id: str,
) -> tuple[tuple[str, ...], VectorSchemaEvidence]:
    errors: list[str] = []
    with psycopg.connect(database_url) as connection:
        type_row = connection.execute(
            """
            SELECT
                format_type(attribute.atttypid, attribute.atttypmod),
                attribute.atttypmod
            FROM pg_catalog.pg_attribute AS attribute
            JOIN pg_catalog.pg_class AS relation ON relation.oid = attribute.attrelid
            JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'public'
              AND relation.relname = 'memories'
              AND attribute.attname = 'embedding'
              AND NOT attribute.attisdropped
            """
        ).fetchone()
        if type_row is None:
            column_type = "missing"
        else:
            base_type = str(type_row[0]).lower()
            type_modifier = int(type_row[1])
            # CockroachDB reports format_type(...) as plain "vector" while
            # storing the declared VECTOR(n) dimension directly in atttypmod.
            column_type = (
                f"vector({type_modifier})"
                if base_type == "vector" and type_modifier > 0
                else base_type
            )
        expected_type = f"vector({expected_dimension})"
        if column_type != expected_type:
            errors.append(f"memories.embedding is {column_type}, expected {expected_type}")

        create_row = connection.execute("SHOW CREATE TABLE public.memories").fetchone()
        create_sql = "" if create_row is None else str(create_row[-1])
        index_present = (
            P3_VECTOR_INDEX in create_sql
            and "VECTOR INDEX" in create_sql.upper()
            and "vector_cosine_ops" in create_sql
        )
        if not index_present:
            errors.append("cosine vector index definition is missing")

        counts = connection.execute(
            """
            SELECT
                count(*) FILTER (WHERE embedding IS NOT NULL),
                count(*) FILTER (
                    WHERE embedding IS NOT NULL
                      AND vector_dims(embedding) = %s
                ),
                count(*) FILTER (
                    WHERE embedding IS NOT NULL
                      AND embedding_provider = %s
                      AND embedding_model_id = %s
                      AND embedding_dimension = %s
                )
            FROM public.memories
            """,
            (
                expected_dimension,
                expected_provider,
                expected_model_id,
                expected_dimension,
            ),
        ).fetchone()
        embedded_count = 0 if counts is None else int(counts[0])
        dimension_count = 0 if counts is None else int(counts[1])
        metadata_count = 0 if counts is None else int(counts[2])
        if embedded_count == 0:
            errors.append("no memories contain embeddings")
        if dimension_count != embedded_count:
            errors.append("one or more stored embeddings have the wrong dimension")
        if metadata_count != embedded_count:
            errors.append("one or more stored embeddings have inconsistent provider metadata")
    return (
        tuple(errors),
        VectorSchemaEvidence(
            column_type=column_type,
            index_name=P3_VECTOR_INDEX,
            index_definition_present=index_present,
            embedded_row_count=embedded_count,
            dimension_match_count=dimension_count,
            metadata_match_count=metadata_count,
        ),
    )
