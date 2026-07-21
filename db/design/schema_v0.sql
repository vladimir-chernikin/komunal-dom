-- Проект схемы Коммуналки Б. НЕ ПРИМЕНЯТЬ до утверждения Владимиром.
-- Собственная БД: komunal_dom_b. Схема намеренно использует обычный PostgreSQL.

BEGIN;

CREATE TABLE organizations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_id bigint REFERENCES organizations(id),
    name text NOT NULL,
    short_name text,
    tax_id text,
    external_key text UNIQUE,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE service_objects (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id bigint NOT NULL REFERENCES organizations(id),
    external_key text UNIQUE,
    name text NOT NULL,
    address_text text NOT NULL,
    fias_id text,
    timezone text NOT NULL DEFAULT 'Europe/Moscow',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE services (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_id bigint REFERENCES services(id),
    external_key text UNIQUE,
    name text NOT NULL,
    description text,
    llm_description text,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE object_services (
    object_id bigint NOT NULL REFERENCES service_objects(id),
    service_id bigint NOT NULL REFERENCES services(id),
    valid_from date,
    valid_to date,
    settings jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (object_id, service_id)
);

CREATE TABLE contacts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id bigint REFERENCES organizations(id),
    object_id bigint REFERENCES service_objects(id),
    full_name text NOT NULL,
    phone text,
    email text,
    external_key text,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE contact_identities (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contact_id bigint NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    channel text NOT NULL,
    channel_user_id text NOT NULL,
    username text,
    verified_at timestamptz,
    UNIQUE (channel, channel_user_id)
);

CREATE TABLE app_settings (
    key text PRIMARY KEY,
    value jsonb NOT NULL,
    description text,
    is_secret boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE prompt_templates (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE,
    purpose text NOT NULL,
    active_version_id bigint,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE prompt_versions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    template_id bigint NOT NULL REFERENCES prompt_templates(id) ON DELETE CASCADE,
    version integer NOT NULL,
    prompt_text text NOT NULL,
    response_schema jsonb,
    model_settings jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (template_id, version)
);

ALTER TABLE prompt_templates
    ADD CONSTRAINT prompt_templates_active_version_fk
    FOREIGN KEY (active_version_id) REFERENCES prompt_versions(id);

CREATE TABLE work_order_statuses (
    code text PRIMARY KEY,
    name text NOT NULL,
    is_final boolean NOT NULL DEFAULT false,
    sort_order integer NOT NULL DEFAULT 0
);

CREATE TABLE work_orders (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    number text NOT NULL UNIQUE,
    organization_id bigint NOT NULL REFERENCES organizations(id),
    object_id bigint NOT NULL REFERENCES service_objects(id),
    service_id bigint NOT NULL REFERENCES services(id),
    requester_contact_id bigint REFERENCES contacts(id),
    status_code text NOT NULL REFERENCES work_order_statuses(code),
    contact_name text NOT NULL,
    contact_phone text NOT NULL,
    problem_text text NOT NULL,
    source_channel text NOT NULL,
    source_session_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE work_order_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    work_order_id bigint NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
    event_type text NOT NULL,
    from_status text REFERENCES work_order_statuses(code),
    to_status text REFERENCES work_order_statuses(code),
    actor_user_id bigint,
    comment text,
    data jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE work_order_files (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    work_order_id bigint NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
    storage_key text NOT NULL UNIQUE,
    original_name text NOT NULL,
    content_type text,
    size_bytes bigint NOT NULL,
    uploaded_by bigint,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE work_order_links (
    from_work_order_id bigint NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
    to_work_order_id bigint NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
    link_type text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (from_work_order_id, to_work_order_id, link_type)
);

CREATE TABLE app_users (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    login text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    contact_id bigint REFERENCES contacts(id),
    display_name text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    is_system_admin boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE roles (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    permissions jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE user_roles (
    user_id bigint NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    role_id bigint NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE user_organization_scopes (
    user_id bigint NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    organization_id bigint NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, organization_id)
);

CREATE TABLE auth_sessions (
    id uuid PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    ip_address inet,
    user_agent text,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE dialog_sessions (
    id text PRIMARY KEY,
    channel text NOT NULL,
    channel_user_id text,
    contact_id bigint REFERENCES contacts(id),
    status text NOT NULL,
    state_version integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    closed_at timestamptz
);

CREATE TABLE dialog_turns (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id text NOT NULL REFERENCES dialog_sessions(id) ON DELETE CASCADE,
    turn_no integer NOT NULL,
    channel_message_id text,
    user_text text,
    bot_text text,
    result_status text NOT NULL,
    duration_ms integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, turn_no)
);

CREATE UNIQUE INDEX dialog_turns_message_key
    ON dialog_turns(session_id, channel_message_id)
    WHERE channel_message_id IS NOT NULL;

CREATE TABLE dialog_state_checkpoints (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id text NOT NULL REFERENCES dialog_sessions(id) ON DELETE CASCADE,
    turn_id bigint REFERENCES dialog_turns(id) ON DELETE CASCADE,
    phase text NOT NULL CHECK (phase IN ('before_turn', 'after_turn', 'order_created')),
    state_version integer NOT NULL,
    state jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, turn_id, phase)
);

CREATE TABLE dialog_trace_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id text NOT NULL REFERENCES dialog_sessions(id) ON DELETE CASCADE,
    turn_id bigint REFERENCES dialog_turns(id) ON DELETE CASCADE,
    step_no smallint NOT NULL,
    step_name text NOT NULL,
    status text NOT NULL,
    input_refs jsonb NOT NULL DEFAULT '{}'::jsonb,
    state_diff jsonb NOT NULL DEFAULT '{}'::jsonb,
    decision jsonb NOT NULL DEFAULT '{}'::jsonb,
    duration_ms integer,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE llm_calls (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id text REFERENCES dialog_sessions(id) ON DELETE SET NULL,
    turn_id bigint REFERENCES dialog_turns(id) ON DELETE SET NULL,
    trace_event_id bigint REFERENCES dialog_trace_events(id) ON DELETE SET NULL,
    purpose text NOT NULL,
    model text NOT NULL,
    prompt_version_id bigint REFERENCES prompt_versions(id),
    request_redacted jsonb NOT NULL,
    response_redacted jsonb,
    parsed_result jsonb,
    status text NOT NULL,
    duration_ms integer NOT NULL,
    tokens_in integer,
    tokens_out integer,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE integration_calls (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id text REFERENCES dialog_sessions(id) ON DELETE SET NULL,
    turn_id bigint REFERENCES dialog_turns(id) ON DELETE SET NULL,
    trace_event_id bigint REFERENCES dialog_trace_events(id) ON DELETE SET NULL,
    integration text NOT NULL,
    operation text NOT NULL,
    request_redacted jsonb NOT NULL,
    response_redacted jsonb,
    status text NOT NULL,
    duration_ms integer NOT NULL,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE admin_audit_log (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id bigint REFERENCES app_users(id) ON DELETE SET NULL,
    action text NOT NULL,
    entity_type text NOT NULL,
    entity_id text,
    before_data jsonb,
    after_data jsonb,
    ip_address inet,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE data_import_runs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_system text NOT NULL,
    entity_type text NOT NULL,
    status text NOT NULL,
    rows_read integer NOT NULL DEFAULT 0,
    rows_written integer NOT NULL DEFAULT 0,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);

CREATE TABLE data_import_errors (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    import_run_id bigint NOT NULL REFERENCES data_import_runs(id) ON DELETE CASCADE,
    source_key text,
    error_code text NOT NULL,
    error_text text NOT NULL,
    source_data_redacted jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE work_order_events
    ADD CONSTRAINT work_order_events_actor_fk
    FOREIGN KEY (actor_user_id) REFERENCES app_users(id) ON DELETE SET NULL;
ALTER TABLE work_order_files
    ADD CONSTRAINT work_order_files_uploader_fk
    FOREIGN KEY (uploaded_by) REFERENCES app_users(id) ON DELETE SET NULL;

CREATE INDEX dialog_trace_session_turn_idx ON dialog_trace_events(session_id, turn_id, step_no);
CREATE INDEX dialog_checkpoint_session_created_idx ON dialog_state_checkpoints(session_id, created_at DESC);
CREATE INDEX llm_calls_session_created_idx ON llm_calls(session_id, created_at DESC);
CREATE INDEX integration_calls_session_created_idx ON integration_calls(session_id, created_at DESC);
CREATE INDEX work_orders_object_created_idx ON work_orders(object_id, created_at DESC);

COMMIT;
