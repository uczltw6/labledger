-- P3: production semantic-memory vectors and provenance metadata.
-- This session setting is required by CockroachDB when creating a vector
-- index on a non-empty table. It is not a cluster-wide setting.
SET sql_safe_updates = false;

ALTER TABLE public.memories
    ADD COLUMN IF NOT EXISTS embedding VECTOR(512) NULL;

ALTER TABLE public.memories
    ADD COLUMN IF NOT EXISTS embedding_provider STRING NULL;

ALTER TABLE public.memories
    ADD COLUMN IF NOT EXISTS embedding_model_id STRING NULL;

ALTER TABLE public.memories
    ADD COLUMN IF NOT EXISTS embedding_dimension INT NULL;

CREATE VECTOR INDEX IF NOT EXISTS ix_memories_embedding_cosine
    ON public.memories (embedding vector_cosine_ops);
