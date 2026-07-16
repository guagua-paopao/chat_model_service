-- Enterprise QA System core schema (reference DDL)
-- PostgreSQL 16+ and pgvector. Convert this file into ordered migrations before production use.
-- The application should generate UUIDv7; gen_random_uuid() is a safe fallback for this reference.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE tenants (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                varchar(64) NOT NULL UNIQUE,
    name                varchar(200) NOT NULL,
    status              varchar(24) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'suspended', 'deleting', 'deleted')),
    default_locale      varchar(16) NOT NULL DEFAULT 'zh-CN',
    timezone            varchar(64) NOT NULL DEFAULT 'Asia/Shanghai',
    settings            jsonb NOT NULL DEFAULT '{}'::jsonb,
    data_classification varchar(24) NOT NULL DEFAULT 'internal'
                        CHECK (data_classification IN ('public', 'internal', 'confidential', 'restricted')),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    deleted_at          timestamptz,
    UNIQUE (id, code)
);

CREATE TABLE users (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id),
    auth_issuer     varchar(512) NOT NULL,
    auth_subject    varchar(255) NOT NULL,
    email           varchar(320),
    display_name    varchar(200) NOT NULL,
    status          varchar(24) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('invited', 'active', 'disabled', 'deleted')),
    locale          varchar(16) NOT NULL DEFAULT 'zh-CN',
    last_login_at   timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    deleted_at      timestamptz,
    UNIQUE (tenant_id, auth_issuer, auth_subject),
    UNIQUE (tenant_id, id)
);

CREATE INDEX users_tenant_status_idx ON users (tenant_id, status) WHERE deleted_at IS NULL;

CREATE TABLE roles (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenants(id),
    code        varchar(64) NOT NULL,
    name        varchar(200) NOT NULL,
    permissions jsonb NOT NULL DEFAULT '[]'::jsonb,
    is_system   boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, code),
    UNIQUE (tenant_id, id)
);

CREATE TABLE user_roles (
    tenant_id   uuid NOT NULL REFERENCES tenants(id),
    user_id     uuid NOT NULL,
    role_id     uuid NOT NULL,
    valid_from  timestamptz NOT NULL DEFAULT now(),
    valid_until timestamptz,
    granted_by  uuid,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, user_id, role_id),
    FOREIGN KEY (tenant_id, user_id) REFERENCES users(tenant_id, id),
    FOREIGN KEY (tenant_id, role_id) REFERENCES roles(tenant_id, id),
    FOREIGN KEY (tenant_id, granted_by) REFERENCES users(tenant_id, id),
    CHECK (valid_until IS NULL OR valid_until > valid_from)
);

CREATE TABLE groups (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenants(id),
    external_id varchar(512),
    name        varchar(200) NOT NULL,
    source      varchar(16) NOT NULL CHECK (source IN ('oidc', 'scim', 'manual')),
    status      varchar(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    synced_at   timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, source, external_id),
    UNIQUE (tenant_id, id)
);

CREATE TABLE group_members (
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    group_id  uuid NOT NULL,
    user_id   uuid NOT NULL,
    source    varchar(16) NOT NULL CHECK (source IN ('oidc', 'scim', 'manual')),
    synced_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, group_id, user_id),
    FOREIGN KEY (tenant_id, group_id) REFERENCES groups(tenant_id, id),
    FOREIGN KEY (tenant_id, user_id) REFERENCES users(tenant_id, id)
);

CREATE TABLE knowledge_bases (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid NOT NULL REFERENCES tenants(id),
    code                            varchar(64) NOT NULL,
    name                            varchar(200) NOT NULL,
    description                     text,
    status                          varchar(24) NOT NULL DEFAULT 'active'
                                    CHECK (status IN ('active', 'archived', 'reindexing')),
    classification                  varchar(24) NOT NULL DEFAULT 'internal'
                                    CHECK (classification IN ('public', 'internal', 'confidential', 'restricted')),
    embedding_config_version_id     uuid NOT NULL,
    retrieval_config_version_id     uuid NOT NULL,
    knowledge_version               bigint NOT NULL DEFAULT 1 CHECK (knowledge_version >= 1),
    created_by                      uuid NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now(),
    deleted_at                      timestamptz,
    UNIQUE (tenant_id, code),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, created_by) REFERENCES users(tenant_id, id)
);

CREATE INDEX knowledge_bases_tenant_status_idx
    ON knowledge_bases (tenant_id, status) WHERE deleted_at IS NULL;

CREATE TABLE documents (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           uuid NOT NULL REFERENCES tenants(id),
    knowledge_base_id   uuid NOT NULL,
    title               varchar(500) NOT NULL,
    source_type         varchar(32) NOT NULL CHECK (source_type IN ('upload', 'url', 'connector', 'api')),
    source_uri          text,
    external_id         varchar(512),
    status              varchar(24) NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft', 'processing', 'ready', 'archived', 'deleting', 'deleted', 'failed')),
    current_version_id  uuid,
    classification      varchar(24) NOT NULL DEFAULT 'internal'
                        CHECK (classification IN ('public', 'internal', 'confidential', 'restricted')),
    acl_mode            varchar(24) NOT NULL DEFAULT 'inherit'
                        CHECK (acl_mode IN ('inherit', 'restricted', 'public_in_tenant')),
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by          uuid NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    deleted_at          timestamptz,
    UNIQUE (tenant_id, id),
    UNIQUE NULLS NOT DISTINCT (tenant_id, knowledge_base_id, source_type, external_id),
    FOREIGN KEY (tenant_id, knowledge_base_id) REFERENCES knowledge_bases(tenant_id, id),
    FOREIGN KEY (tenant_id, created_by) REFERENCES users(tenant_id, id)
);

CREATE INDEX documents_kb_status_idx
    ON documents (tenant_id, knowledge_base_id, status) WHERE deleted_at IS NULL;
CREATE INDEX documents_metadata_gin_idx ON documents USING gin (metadata);

CREATE TABLE document_versions (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       uuid NOT NULL REFERENCES tenants(id),
    document_id                     uuid NOT NULL,
    version_no                      integer NOT NULL CHECK (version_no >= 1),
    filename                        varchar(512) NOT NULL,
    mime_type                       varchar(255) NOT NULL,
    size_bytes                      bigint NOT NULL CHECK (size_bytes > 0),
    sha256                          char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    object_key                      text NOT NULL,
    parser_name                     varchar(128),
    parser_version                  varchar(64),
    chunk_config_version_id         uuid NOT NULL,
    embedding_config_version_id     uuid NOT NULL,
    language                        varchar(16),
    page_count                      integer CHECK (page_count IS NULL OR page_count >= 0),
    status                          varchar(24) NOT NULL DEFAULT 'staged'
                                    CHECK (status IN ('staged', 'published', 'superseded', 'rejected', 'failed', 'deleted')),
    published_at                    timestamptz,
    created_by                      uuid NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, document_id, version_no),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, object_key),
    FOREIGN KEY (tenant_id, document_id) REFERENCES documents(tenant_id, id),
    FOREIGN KEY (tenant_id, created_by) REFERENCES users(tenant_id, id)
);

ALTER TABLE documents
    ADD CONSTRAINT documents_current_version_fk
    FOREIGN KEY (tenant_id, current_version_id)
    REFERENCES document_versions(tenant_id, id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE INDEX document_versions_document_status_idx
    ON document_versions (tenant_id, document_id, status, version_no DESC);
CREATE INDEX document_versions_content_hash_idx
    ON document_versions (tenant_id, sha256);

CREATE TABLE document_acl (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id),
    document_id     uuid NOT NULL,
    principal_type  varchar(16) NOT NULL CHECK (principal_type IN ('user', 'group', 'role')),
    principal_id    uuid NOT NULL,
    permission      varchar(16) NOT NULL CHECK (permission IN ('read', 'manage')),
    effect          varchar(8) NOT NULL DEFAULT 'allow' CHECK (effect = 'allow'),
    created_by      uuid NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, document_id, principal_type, principal_id, permission),
    FOREIGN KEY (tenant_id, document_id) REFERENCES documents(tenant_id, id),
    FOREIGN KEY (tenant_id, created_by) REFERENCES users(tenant_id, id)
);

CREATE INDEX document_acl_principal_idx
    ON document_acl (tenant_id, principal_type, principal_id, permission, document_id);

-- The reference fixes vector dimension at 1536. A different embedding dimension requires a new
-- table/column/index version or an approved typmod migration; never mix dimensions silently.
CREATE TABLE document_chunks (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           uuid NOT NULL REFERENCES tenants(id),
    knowledge_base_id   uuid NOT NULL,
    document_id         uuid NOT NULL,
    document_version_id uuid NOT NULL,
    sequence_no         integer NOT NULL CHECK (sequence_no >= 0),
    content             text NOT NULL CHECK (length(content) > 0),
    content_hash        char(64) NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    token_count         integer NOT NULL CHECK (token_count > 0),
    page_from           integer CHECK (page_from IS NULL OR page_from >= 1),
    page_to             integer CHECK (page_to IS NULL OR page_to >= page_from),
    section_path        text[] NOT NULL DEFAULT '{}'::text[],
    char_start          integer CHECK (char_start IS NULL OR char_start >= 0),
    char_end            integer CHECK (char_end IS NULL OR char_end >= char_start),
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    search_text         tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content, ''))) STORED,
    embedding           vector(1536) NOT NULL,
    status              varchar(16) NOT NULL DEFAULT 'staged'
                        CHECK (status IN ('staged', 'active', 'inactive', 'deleted')),
    created_at          timestamptz NOT NULL DEFAULT now(),
    deleted_at          timestamptz,
    UNIQUE (tenant_id, document_version_id, sequence_no),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, knowledge_base_id) REFERENCES knowledge_bases(tenant_id, id),
    FOREIGN KEY (tenant_id, document_id) REFERENCES documents(tenant_id, id),
    FOREIGN KEY (tenant_id, document_version_id) REFERENCES document_versions(tenant_id, id)
);

CREATE INDEX document_chunks_scope_idx
    ON document_chunks (tenant_id, knowledge_base_id, status, document_version_id);
CREATE INDEX document_chunks_document_idx
    ON document_chunks (tenant_id, document_id, document_version_id, sequence_no);
CREATE INDEX document_chunks_search_gin_idx ON document_chunks USING gin (search_text);
CREATE INDEX document_chunks_embedding_hnsw_idx
    ON document_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE TABLE ingestion_jobs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           uuid NOT NULL REFERENCES tenants(id),
    document_id         uuid NOT NULL,
    document_version_id uuid NOT NULL,
    status              varchar(24) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'running', 'retrying', 'succeeded', 'failed', 'cancelled', 'dead_letter')),
    stage               varchar(24) NOT NULL
                        CHECK (stage IN ('scan', 'parse', 'chunk', 'embed', 'index', 'publish', 'delete')),
    progress            numeric(5,2) NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    attempt             integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    max_attempts        integer NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),
    idempotency_key     varchar(128) NOT NULL,
    error_code          varchar(64),
    error_detail_safe   text,
    metrics             jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at          timestamptz,
    finished_at         timestamptz,
    next_retry_at       timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, idempotency_key),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, document_id) REFERENCES documents(tenant_id, id),
    FOREIGN KEY (tenant_id, document_version_id) REFERENCES document_versions(tenant_id, id)
);

CREATE INDEX ingestion_jobs_poll_idx
    ON ingestion_jobs (status, next_retry_at, created_at)
    WHERE status IN ('pending', 'retrying');
CREATE INDEX ingestion_jobs_document_idx
    ON ingestion_jobs (tenant_id, document_id, created_at DESC);

CREATE TABLE conversations (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           uuid NOT NULL REFERENCES tenants(id),
    user_id             uuid NOT NULL,
    title               varchar(300) NOT NULL DEFAULT '新对话',
    status              varchar(16) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'archived', 'deleted')),
    channel             varchar(32) NOT NULL CHECK (channel IN ('web', 'api', 'approved_connector')),
    default_kb_ids      uuid[] NOT NULL DEFAULT '{}'::uuid[],
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    deleted_at          timestamptz,
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, user_id) REFERENCES users(tenant_id, id)
);

CREATE INDEX conversations_user_updated_idx
    ON conversations (tenant_id, user_id, updated_at DESC, id DESC)
    WHERE deleted_at IS NULL;

CREATE TABLE messages (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           uuid NOT NULL REFERENCES tenants(id),
    conversation_id     uuid NOT NULL,
    parent_message_id   uuid,
    role                varchar(16) NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content             text NOT NULL DEFAULT '',
    content_format      varchar(16) NOT NULL DEFAULT 'markdown'
                        CHECK (content_format IN ('text', 'markdown', 'json')),
    status              varchar(16) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'streaming', 'completed', 'failed', 'cancelled', 'blocked')),
    sequence_no         bigint NOT NULL CHECK (sequence_no >= 1),
    model_route_id      varchar(128),
    model_name          varchar(256),
    prompt_version_id   uuid,
    retrieval_run_id    uuid,
    input_tokens        integer CHECK (input_tokens IS NULL OR input_tokens >= 0),
    output_tokens       integer CHECK (output_tokens IS NULL OR output_tokens >= 0),
    cost_amount         numeric(20,8) CHECK (cost_amount IS NULL OR cost_amount >= 0),
    cost_currency       char(3),
    finish_reason       varchar(32)
                        CHECK (finish_reason IS NULL OR finish_reason IN ('stop', 'length', 'cancelled', 'content_filter', 'error')),
    safety_labels       jsonb NOT NULL DEFAULT '{}'::jsonb,
    provider_request_id varchar(256),
    trace_id            varchar(64),
    latency_ms          integer CHECK (latency_ms IS NULL OR latency_ms >= 0),
    first_token_ms      integer CHECK (first_token_ms IS NULL OR first_token_ms >= 0),
    error_code          varchar(64),
    created_at          timestamptz NOT NULL DEFAULT now(),
    completed_at        timestamptz,
    deleted_at          timestamptz,
    UNIQUE (tenant_id, conversation_id, sequence_no),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations(tenant_id, id),
    FOREIGN KEY (tenant_id, parent_message_id) REFERENCES messages(tenant_id, id)
);

CREATE INDEX messages_conversation_sequence_idx
    ON messages (tenant_id, conversation_id, sequence_no);
CREATE INDEX messages_streaming_idx
    ON messages (status, created_at) WHERE status IN ('pending', 'streaming');

CREATE TABLE retrieval_runs (
    id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                   uuid NOT NULL REFERENCES tenants(id),
    message_id                  uuid NOT NULL,
    normalized_query            text,
    query_hash                  char(64) NOT NULL,
    knowledge_base_ids          uuid[] NOT NULL,
    retrieval_config_version_id uuid NOT NULL,
    acl_fingerprint             char(64) NOT NULL,
    candidate_count             integer NOT NULL DEFAULT 0 CHECK (candidate_count >= 0),
    returned_count              integer NOT NULL DEFAULT 0 CHECK (returned_count >= 0),
    top_score                   numeric(10,8),
    latency_ms                  integer NOT NULL CHECK (latency_ms >= 0),
    cache_hit                   boolean NOT NULL DEFAULT false,
    created_at                  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, message_id),
    FOREIGN KEY (tenant_id, message_id) REFERENCES messages(tenant_id, id)
);

ALTER TABLE messages
    ADD CONSTRAINT messages_retrieval_run_fk
    FOREIGN KEY (tenant_id, retrieval_run_id)
    REFERENCES retrieval_runs(tenant_id, id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE retrieval_hits (
    tenant_id           uuid NOT NULL REFERENCES tenants(id),
    retrieval_run_id    uuid NOT NULL,
    chunk_id            uuid NOT NULL,
    rank                integer NOT NULL CHECK (rank >= 1),
    vector_score        numeric(10,8),
    keyword_score       numeric(10,8),
    rerank_score        numeric(10,8),
    selected_for_context boolean NOT NULL DEFAULT false,
    token_count         integer NOT NULL CHECK (token_count >= 0),
    created_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, retrieval_run_id, chunk_id),
    UNIQUE (tenant_id, retrieval_run_id, rank),
    FOREIGN KEY (tenant_id, retrieval_run_id) REFERENCES retrieval_runs(tenant_id, id),
    FOREIGN KEY (tenant_id, chunk_id) REFERENCES document_chunks(tenant_id, id)
);

CREATE TABLE message_citations (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           uuid NOT NULL REFERENCES tenants(id),
    message_id          uuid NOT NULL,
    chunk_id            uuid NOT NULL,
    ordinal             integer NOT NULL CHECK (ordinal >= 1),
    document_id         uuid NOT NULL,
    document_version_id uuid NOT NULL,
    page_from           integer,
    page_to             integer,
    quote_start         integer,
    quote_end           integer,
    display_quote       text CHECK (display_quote IS NULL OR length(display_quote) <= 1200),
    relevance_score     numeric(10,8),
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, message_id, ordinal),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, message_id) REFERENCES messages(tenant_id, id),
    FOREIGN KEY (tenant_id, chunk_id) REFERENCES document_chunks(tenant_id, id),
    FOREIGN KEY (tenant_id, document_id) REFERENCES documents(tenant_id, id),
    FOREIGN KEY (tenant_id, document_version_id) REFERENCES document_versions(tenant_id, id),
    CHECK (page_to IS NULL OR page_from IS NULL OR page_to >= page_from),
    CHECK (quote_end IS NULL OR quote_start IS NULL OR quote_end >= quote_start)
);

CREATE TABLE feedback (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id),
    message_id      uuid NOT NULL,
    user_id         uuid NOT NULL,
    rating          smallint NOT NULL CHECK (rating IN (-1, 1)),
    reason_code     varchar(32) NOT NULL
                    CHECK (reason_code IN ('helpful', 'incorrect', 'factually_unsupported', 'incorrect_citation', 'outdated', 'unsafe', 'other')),
    comment         varchar(2000),
    expected_answer text,
    status          varchar(16) NOT NULL DEFAULT 'new'
                    CHECK (status IN ('new', 'reviewed', 'actioned', 'dismissed')),
    tags            text[] NOT NULL DEFAULT '{}'::text[],
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    reviewed_by     uuid,
    reviewed_at     timestamptz,
    UNIQUE (tenant_id, message_id, user_id),
    FOREIGN KEY (tenant_id, message_id) REFERENCES messages(tenant_id, id),
    FOREIGN KEY (tenant_id, user_id) REFERENCES users(tenant_id, id),
    FOREIGN KEY (tenant_id, reviewed_by) REFERENCES users(tenant_id, id)
);

CREATE TABLE usage_ledger (
    id              uuid NOT NULL DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id),
    user_id         uuid,
    request_id      varchar(128) NOT NULL,
    message_id      uuid,
    provider        varchar(128) NOT NULL,
    model           varchar(256) NOT NULL,
    operation       varchar(16) NOT NULL CHECK (operation IN ('chat', 'embed', 'rerank')),
    input_tokens    bigint NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens   bigint NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    cached_tokens   bigint NOT NULL DEFAULT 0 CHECK (cached_tokens >= 0),
    amount          numeric(20,8) NOT NULL DEFAULT 0,
    currency        char(3) NOT NULL DEFAULT 'USD',
    price_version   varchar(64) NOT NULL,
    estimated       boolean NOT NULL DEFAULT false,
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (occurred_at, id),
    FOREIGN KEY (tenant_id, user_id) REFERENCES users(tenant_id, id),
    FOREIGN KEY (tenant_id, message_id) REFERENCES messages(tenant_id, id)
) PARTITION BY RANGE (occurred_at);

-- Create monthly partitions ahead of time in migrations, for example:
-- CREATE TABLE usage_ledger_2026_07 PARTITION OF usage_ledger
-- FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');

CREATE TABLE audit_logs (
    id                  uuid NOT NULL DEFAULT gen_random_uuid(),
    occurred_at         timestamptz NOT NULL DEFAULT now(),
    tenant_id           uuid NOT NULL REFERENCES tenants(id),
    actor_type          varchar(16) NOT NULL CHECK (actor_type IN ('user', 'service', 'system')),
    actor_id            uuid,
    actor_display_safe  varchar(200),
    action              varchar(128) NOT NULL,
    resource_type       varchar(64) NOT NULL,
    resource_id         uuid,
    result              varchar(16) NOT NULL CHECK (result IN ('success', 'denied', 'failure')),
    request_id          varchar(128),
    trace_id            varchar(64),
    source_ip_hash      char(64),
    user_agent_class    varchar(64),
    changes             jsonb NOT NULL DEFAULT '{}'::jsonb,
    reason              text,
    approval_id         varchar(128),
    prev_hash           char(64),
    event_hash          char(64),
    PRIMARY KEY (occurred_at, id)
) PARTITION BY RANGE (occurred_at);

-- The application audit role must have INSERT only. Create monthly partitions before use.
CREATE INDEX audit_logs_tenant_time_idx ON audit_logs (tenant_id, occurred_at DESC);
CREATE INDEX audit_logs_resource_idx ON audit_logs (tenant_id, resource_type, resource_id, occurred_at DESC);

CREATE TABLE outbox_events (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id),
    aggregate_type  varchar(64) NOT NULL,
    aggregate_id    uuid NOT NULL,
    event_type      varchar(128) NOT NULL,
    event_version   integer NOT NULL DEFAULT 1 CHECK (event_version >= 1),
    payload         jsonb NOT NULL,
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    published_at    timestamptz,
    attempts        integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error_safe text
);

CREATE INDEX outbox_events_unpublished_idx
    ON outbox_events (occurred_at, id) WHERE published_at IS NULL;

CREATE TABLE idempotency_records (
    tenant_id          uuid NOT NULL REFERENCES tenants(id),
    actor_id           uuid NOT NULL,
    key                varchar(128) NOT NULL,
    operation          varchar(128) NOT NULL,
    request_hash       char(64) NOT NULL,
    status             varchar(16) NOT NULL CHECK (status IN ('processing', 'completed', 'failed')),
    response_code      integer,
    response_body_ref  text,
    created_at         timestamptz NOT NULL DEFAULT now(),
    expires_at         timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, actor_id, operation, key),
    CHECK (expires_at > created_at)
);

CREATE INDEX idempotency_records_expiry_idx ON idempotency_records (expires_at);

-- Optional RLS defense in depth. The application must SET LOCAL app.tenant_id inside each
-- transaction and clear context before returning a pooled connection. Apply/test table by table.
-- ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE documents FORCE ROW LEVEL SECURITY;
-- CREATE POLICY documents_tenant_isolation ON documents
--   USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
--   WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- S5 runtime governance delta. The executable source of truth remains Alembic 0005/0006;
-- these tables document the production PostgreSQL target shape.
ALTER TABLE users ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1;
ALTER TABLE users ADD COLUMN IF NOT EXISTS identity_synced_at timestamptz;
ALTER TABLE users ADD COLUMN IF NOT EXISTS disabled_at timestamptz;

CREATE TABLE groups (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    code varchar(128) NOT NULL,
    display_name varchar(200) NOT NULL,
    external_id varchar(255),
    status varchar(24) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    identity_synced_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, code),
    UNIQUE (tenant_id, id)
);

CREATE TABLE group_members (
    tenant_id uuid NOT NULL,
    group_id uuid NOT NULL,
    user_id uuid NOT NULL,
    source varchar(32) NOT NULL DEFAULT 'directory',
    valid_from timestamptz NOT NULL DEFAULT now(),
    valid_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, group_id, user_id),
    FOREIGN KEY (tenant_id, group_id) REFERENCES groups(tenant_id, id),
    FOREIGN KEY (tenant_id, user_id) REFERENCES users(tenant_id, id)
);
CREATE INDEX group_members_user_idx ON group_members (tenant_id, user_id);

CREATE TABLE rag_configs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    code varchar(64) NOT NULL,
    version integer NOT NULL CHECK (version >= 1),
    status varchar(24) NOT NULL CHECK (
        status IN ('draft', 'evaluated', 'approved', 'published', 'archived')
    ),
    prompt_version varchar(64) NOT NULL,
    prompt_template text NOT NULL,
    config_json jsonb NOT NULL,
    checksum char(64) NOT NULL,
    evaluation_status varchar(24) NOT NULL CHECK (
        evaluation_status IN ('pending', 'passed', 'failed')
    ),
    change_reason varchar(500) NOT NULL,
    supersedes_id uuid,
    rollback_of_id uuid,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    approved_by uuid,
    approved_at timestamptz,
    approval_id varchar(128),
    published_by uuid,
    published_at timestamptz,
    UNIQUE (tenant_id, code, version),
    UNIQUE (tenant_id, id)
);
CREATE INDEX rag_configs_published_idx
    ON rag_configs (tenant_id, code, status, version DESC);

CREATE TABLE rag_config_evaluations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    rag_config_id uuid NOT NULL REFERENCES rag_configs(id),
    dataset_version varchar(128) NOT NULL,
    dataset_checksum char(64) NOT NULL,
    evaluator_version varchar(64) NOT NULL,
    status varchar(24) NOT NULL CHECK (status = 'completed'),
    gate_result varchar(16) NOT NULL CHECK (gate_result IN ('passed', 'failed')),
    metrics jsonb NOT NULL,
    thresholds jsonb NOT NULL,
    failed_checks jsonb NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (tenant_id, id)
);

CREATE TABLE quota_policies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    scope_type varchar(16) NOT NULL CHECK (scope_type IN ('tenant', 'user')),
    scope_id varchar(128) NOT NULL,
    requests_per_minute integer NOT NULL CHECK (requests_per_minute > 0),
    concurrent_requests integer NOT NULL CHECK (concurrent_requests > 0),
    daily_token_limit integer NOT NULL CHECK (daily_token_limit > 0),
    monthly_cost_limit numeric(18,8) NOT NULL CHECK (monthly_cost_limit >= 0),
    currency char(3) NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    version integer NOT NULL DEFAULT 1,
    created_by uuid NOT NULL,
    updated_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, scope_type, scope_id),
    UNIQUE (tenant_id, id)
);

CREATE TABLE quota_windows (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    user_id uuid NOT NULL,
    window_kind varchar(16) NOT NULL,
    window_start timestamptz NOT NULL,
    request_count integer NOT NULL DEFAULT 0,
    input_tokens_reserved integer NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, user_id, window_kind, window_start)
);

CREATE TABLE quota_leases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    user_id uuid NOT NULL,
    input_tokens_reserved integer NOT NULL DEFAULT 0,
    acquired_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);
CREATE INDEX quota_leases_tenant_expiry_idx ON quota_leases (tenant_id, expires_at);
CREATE UNIQUE INDEX rag_configs_one_published_uq
    ON rag_configs (tenant_id, code) WHERE status = 'published';

CREATE TABLE governance_audit_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    sequence_no integer NOT NULL,
    actor_user_id uuid NOT NULL,
    action varchar(128) NOT NULL,
    resource_type varchar(64) NOT NULL,
    resource_id varchar(128) NOT NULL,
    result varchar(16) NOT NULL,
    reason varchar(500) NOT NULL,
    approval_id varchar(128),
    request_id varchar(128) NOT NULL,
    trace_id varchar(64),
    details_safe jsonb NOT NULL DEFAULT '{}'::jsonb,
    previous_hash char(64) NOT NULL,
    event_hash char(64) NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, sequence_no)
);

CREATE TABLE security_incidents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    title varchar(300) NOT NULL,
    category varchar(64) NOT NULL,
    severity varchar(8) NOT NULL CHECK (severity IN ('P0', 'P1', 'P2', 'P3')),
    status varchar(24) NOT NULL CHECK (
        status IN ('open', 'triaged', 'contained', 'resolved', 'closed')
    ),
    evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    owner_user_id uuid NOT NULL,
    resolution_safe varchar(1000),
    version integer NOT NULL DEFAULT 1,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    UNIQUE (tenant_id, id)
);
