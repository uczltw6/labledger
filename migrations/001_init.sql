-- LabLedger P2 structured-memory schema.
-- P3 owns semantic embedding storage and its distributed index.

CREATE TABLE IF NOT EXISTS public.devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lab_id UUID NOT NULL,
    name STRING NOT NULL,
    device_type STRING NOT NULL,
    vendor STRING NULL,
    model STRING NULL,
    resource_hint STRING NULL,
    connection_state STRING NOT NULL,
    firmware_version STRING NULL,
    active_calibration_id UUID NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp(),
    CONSTRAINT uq_devices_lab_name UNIQUE (lab_id, name),
    CONSTRAINT ck_devices_connection_state
        CHECK (connection_state IN ('disconnected', 'connected', 'fault')),
    CONSTRAINT ck_devices_timestamp_order CHECK (updated_at >= created_at)
);

CREATE TABLE IF NOT EXISTS public.experiment_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name STRING NOT NULL,
    status STRING NOT NULL,
    recipe_version STRING NOT NULL,
    started_at TIMESTAMPTZ NULL,
    ended_at TIMESTAMPTZ NULL,
    current_step INT NOT NULL DEFAULT 0,
    context JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_by STRING NOT NULL,
    CONSTRAINT ck_experiment_runs_status
        CHECK (status IN ('planned', 'running', 'paused', 'failed', 'completed')),
    CONSTRAINT ck_experiment_runs_step CHECK (current_step >= 0),
    CONSTRAINT ck_experiment_runs_timestamp_order
        CHECK (ended_at IS NULL OR (started_at IS NOT NULL AND ended_at >= started_at))
);

CREATE TABLE IF NOT EXISTS public.artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_run_id UUID NOT NULL,
    artifact_type STRING NOT NULL,
    s3_uri STRING NOT NULL,
    sha256 STRING NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp(),
    CONSTRAINT fk_artifacts_run
        FOREIGN KEY (experiment_run_id) REFERENCES public.experiment_runs (id),
    CONSTRAINT ck_artifacts_sha256 CHECK (length(sha256) = 64)
);

CREATE INDEX IF NOT EXISTS ix_artifacts_run_created
    ON public.artifacts (experiment_run_id, created_at DESC, id);

CREATE TABLE IF NOT EXISTS public.observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_run_id UUID NOT NULL,
    device_id UUID NULL,
    trace_order INT NOT NULL,
    observation_type STRING NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::JSONB,
    summary STRING NOT NULL,
    severity STRING NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    artifact_id UUID NULL,
    provenance JSONB NOT NULL DEFAULT '{}'::JSONB,
    CONSTRAINT fk_observations_run
        FOREIGN KEY (experiment_run_id) REFERENCES public.experiment_runs (id),
    CONSTRAINT fk_observations_device FOREIGN KEY (device_id) REFERENCES public.devices (id),
    CONSTRAINT fk_observations_artifact
        FOREIGN KEY (artifact_id) REFERENCES public.artifacts (id),
    CONSTRAINT uq_observations_run_order UNIQUE (experiment_run_id, trace_order),
    CONSTRAINT ck_observations_trace_order CHECK (trace_order > 0)
);

CREATE TABLE IF NOT EXISTS public.actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_run_id UUID NOT NULL,
    device_id UUID NULL,
    trace_order INT NOT NULL,
    action_type STRING NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}'::JSONB,
    risk_level STRING NOT NULL,
    approval_state STRING NOT NULL,
    selected_reason STRING NOT NULL,
    memory_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
    status STRING NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    executed_at TIMESTAMPTZ NULL,
    CONSTRAINT fk_actions_run
        FOREIGN KEY (experiment_run_id) REFERENCES public.experiment_runs (id),
    CONSTRAINT fk_actions_device FOREIGN KEY (device_id) REFERENCES public.devices (id),
    CONSTRAINT uq_actions_run_order UNIQUE (experiment_run_id, trace_order),
    CONSTRAINT ck_actions_trace_order CHECK (trace_order > 0),
    CONSTRAINT ck_actions_risk_level CHECK (risk_level IN ('low', 'medium', 'high')),
    CONSTRAINT ck_actions_approval_state
        CHECK (approval_state IN ('not_required', 'pending', 'approved', 'rejected')),
    CONSTRAINT ck_actions_timestamp_order
        CHECK (executed_at IS NULL OR executed_at >= created_at)
);

CREATE TABLE IF NOT EXISTS public.outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action_id UUID NOT NULL,
    trace_order INT NOT NULL,
    success BOOL NOT NULL,
    result JSONB NOT NULL DEFAULT '{}'::JSONB,
    quality_delta FLOAT8 NULL,
    error_code STRING NULL,
    summary STRING NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT fk_outcomes_action FOREIGN KEY (action_id) REFERENCES public.actions (id),
    CONSTRAINT uq_outcomes_action UNIQUE (action_id),
    CONSTRAINT ck_outcomes_trace_order CHECK (trace_order > 0)
);

CREATE TABLE IF NOT EXISTS public.calibrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID NOT NULL,
    version STRING NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}'::JSONB,
    status STRING NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ NULL,
    superseded_by UUID NULL,
    confidence FLOAT8 NOT NULL,
    provenance JSONB NOT NULL DEFAULT '{}'::JSONB,
    CONSTRAINT fk_calibrations_device FOREIGN KEY (device_id) REFERENCES public.devices (id),
    CONSTRAINT fk_calibrations_superseded_by
        FOREIGN KEY (superseded_by) REFERENCES public.calibrations (id),
    CONSTRAINT uq_calibrations_device_version UNIQUE (device_id, version),
    CONSTRAINT ck_calibrations_status
        CHECK (status IN ('active', 'superseded', 'expired', 'invalid')),
    CONSTRAINT ck_calibrations_confidence CHECK (confidence BETWEEN 0.0 AND 1.0),
    CONSTRAINT ck_calibrations_validity
        CHECK (valid_until IS NULL OR valid_until > valid_from),
    CONSTRAINT ck_calibrations_not_self_superseded
        CHECK (superseded_by IS NULL OR superseded_by <> id)
);

CREATE INDEX IF NOT EXISTS ix_calibrations_device_status
    ON public.calibrations (device_id, status, valid_from DESC, id);

CREATE TABLE IF NOT EXISTS public.device_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID NOT NULL,
    experiment_run_id UUID NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    connection_result STRING NOT NULL,
    identity_response STRING NULL,
    error_code STRING NULL,
    error_detail STRING NULL,
    recovery_action_id UUID NULL,
    CONSTRAINT fk_device_sessions_device FOREIGN KEY (device_id) REFERENCES public.devices (id),
    CONSTRAINT fk_device_sessions_run
        FOREIGN KEY (experiment_run_id) REFERENCES public.experiment_runs (id),
    CONSTRAINT fk_device_sessions_recovery_action
        FOREIGN KEY (recovery_action_id) REFERENCES public.actions (id),
    CONSTRAINT ck_device_sessions_timestamp_order
        CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE INDEX IF NOT EXISTS ix_device_sessions_device_started
    ON public.device_sessions (device_id, started_at DESC, id);

CREATE INDEX IF NOT EXISTS ix_device_sessions_run_started
    ON public.device_sessions (experiment_run_id, started_at DESC, id);

CREATE TABLE IF NOT EXISTS public.memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lab_id UUID NOT NULL,
    experiment_run_id UUID NULL,
    device_id UUID NULL,
    memory_type STRING NOT NULL,
    title STRING NOT NULL,
    content STRING NOT NULL,
    embedding_text STRING NOT NULL,
    status STRING NOT NULL,
    confidence FLOAT8 NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ NULL,
    superseded_by UUID NULL,
    source_observation_id UUID NULL,
    source_action_id UUID NULL,
    source_outcome_id UUID NULL,
    provenance JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp(),
    CONSTRAINT fk_memories_run
        FOREIGN KEY (experiment_run_id) REFERENCES public.experiment_runs (id),
    CONSTRAINT fk_memories_device FOREIGN KEY (device_id) REFERENCES public.devices (id),
    CONSTRAINT fk_memories_superseded_by FOREIGN KEY (superseded_by) REFERENCES public.memories (id),
    CONSTRAINT fk_memories_source_observation
        FOREIGN KEY (source_observation_id) REFERENCES public.observations (id),
    CONSTRAINT fk_memories_source_action
        FOREIGN KEY (source_action_id) REFERENCES public.actions (id),
    CONSTRAINT fk_memories_source_outcome
        FOREIGN KEY (source_outcome_id) REFERENCES public.outcomes (id),
    CONSTRAINT ck_memories_type CHECK (
        memory_type IN (
            'connection_failure',
            'connection_recovery',
            'experimental_outcome',
            'calibration_fact',
            'intervention_result',
            'operational_rule'
        )
    ),
    CONSTRAINT ck_memories_status
        CHECK (status IN ('active', 'superseded', 'expired', 'disputed')),
    CONSTRAINT ck_memories_confidence CHECK (confidence BETWEEN 0.0 AND 1.0),
    CONSTRAINT ck_memories_validity CHECK (valid_until IS NULL OR valid_until > valid_from),
    CONSTRAINT ck_memories_not_self_superseded
        CHECK (superseded_by IS NULL OR superseded_by <> id)
);

CREATE INDEX IF NOT EXISTS ix_memories_scope_status_type
    ON public.memories (lab_id, status, memory_type, created_at DESC, id);

CREATE TABLE IF NOT EXISTS public.agent_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_run_id UUID NOT NULL,
    step_no INT NOT NULL,
    agent_state JSONB NOT NULL,
    last_action_id UUID NULL,
    pending_action_id UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp(),
    CONSTRAINT fk_agent_checkpoints_run
        FOREIGN KEY (experiment_run_id) REFERENCES public.experiment_runs (id),
    CONSTRAINT fk_agent_checkpoints_last_action
        FOREIGN KEY (last_action_id) REFERENCES public.actions (id),
    CONSTRAINT fk_agent_checkpoints_pending_action
        FOREIGN KEY (pending_action_id) REFERENCES public.actions (id),
    CONSTRAINT uq_agent_checkpoints_run_step UNIQUE (experiment_run_id, step_no),
    CONSTRAINT ck_agent_checkpoints_step CHECK (step_no >= 0)
);

CREATE INDEX IF NOT EXISTS ix_agent_checkpoints_latest
    ON public.agent_checkpoints (experiment_run_id, step_no DESC, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS public.audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_run_id UUID NULL,
    sequence_no INT NULL,
    actor_type STRING NOT NULL,
    actor_id STRING NOT NULL,
    event_type STRING NOT NULL,
    target_type STRING NOT NULL,
    target_id UUID NULL,
    detail JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp(),
    CONSTRAINT fk_audit_events_run
        FOREIGN KEY (experiment_run_id) REFERENCES public.experiment_runs (id),
    CONSTRAINT uq_audit_events_run_sequence UNIQUE (experiment_run_id, sequence_no),
    CONSTRAINT ck_audit_events_sequence CHECK (sequence_no IS NULL OR sequence_no > 0)
);

CREATE INDEX IF NOT EXISTS ix_audit_events_run_created
    ON public.audit_events (experiment_run_id, created_at DESC, id);
