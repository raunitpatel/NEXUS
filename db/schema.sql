-- NEXUS - full DDL for all 7 table

-- TABLE: users

CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    display_name    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT users_email_length CHECK (char_length(email) <= 320),
    CONSTRAINT users_display_name_length CHECK (display_name IS NULL OR char_length(display_name) <= 100)
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- TABLE: agents

CREATE TABLE IF NOT EXISTS agents (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL UNIQUE,
    type          TEXT NOT NULL,
    base_url       TEXT NOT NULL,
    description   TEXT,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT agents_type_values CHECK (type IN ('search', 'code', 'memory', 'tool', 'orchestrator')),
    CONSTRAINT agents_name_length CHECK (char_length(name) <= 100),
    CONSTRAINT agents_base_url_format CHECK (base_url ~ '^https?://')
);

CREATE INDEX IF NOT EXISTS idx_agents_type ON agents (type);
CREATE INDEX IF NOT EXISTS idx_agents_is_active ON agents (is_active);

-- TABLE: runs

CREATE TABLE IF NOT EXISTS runs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    query         TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    output        TEXT,
    error         TEXT,
    metadata      JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at  TIMESTAMPTZ,

    CONSTRAINT runs_status_values CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    CONSTRAINT runs_query_not_empty CHECK (char_length(trim(query)) > 0),
    CONSTRAINT runs_query_length CHECK (char_length(query) <= 4096),
    CONSTRAINT runs_completed_at_only_when_terminal CHECK (
        completed_at IS NULL OR status IN ('completed', 'failed', 'cancelled')
    )
);

CREATE INDEX IF NOT EXISTS idx_runs_user_id_created_at ON runs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs (status);
CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs (created_at DESC);


-- TABLE: tasks

CREATE TABLE IF NOT EXISTS tasks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id        UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    agent_id      UUID REFERENCES agents(id) ON DELETE SET NULL,
    type          TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    input         JSONB NOT NULL DEFAULT '{}',
    output        JSONB,
    error         TEXT,
    attempt       INT NOT NULL DEFAULT 1,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at  TIMESTAMPTZ,

    CONSTRAINT tasks_status_values CHECK (status IN ('pending', 'running', 'completed', 'failed', 'retrying')),
    CONSTRAINT tasks_type_values CHECK (type IN ('search', 'code', 'memory_read', 'memory_write', 'tool', 'synthesize')),
    CONSTRAINT tasks_attempt_positive CHECK (attempt >= 1),
    CONSTRAINT tasks_attempt_max CHECK (attempt <= 5)
);

CREATE INDEX IF NOT EXISTS idx_tasks_run_id ON tasks (run_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status);
CREATE INDEX IF NOT EXISTS idx_tasks_agent_id ON tasks (agent_id);
CREATE INDEX IF NOT EXISTS idx_tasks_run_id_status ON tasks (run_id, status);

-- TABLE: events

CREATE TABLE IF NOT EXISTS events (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id        UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    task_id       UUID REFERENCES tasks(id) ON DELETE CASCADE,
    type          TEXT NOT NULL,
    payload       JSONB NOT NULL DEFAULT '{}',
    source        TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT events_type_values CHECK (type IN (
        'thought', 'tool_call', 'tool_result', 'agent_start', 'agent_end',
        'orchestrator_plan', 'orchestrator_dispatch', 'orchestrator_synthesize',
        'run_start', 'run_complete', 'run_error', 'memory_read', 'memory_write'
    )),
    CONSTRAINT events_source_not_empty CHECK (char_length(trim(source)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_events_run_id_created_at ON events (run_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_events_task_id ON events (task_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events (type);

-- TABLE: tool_results

CREATE TABLE IF NOT EXISTS tool_results (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id       UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    tool_name     TEXT NOT NULL,
    input         JSONB NOT NULL DEFAULT '{}',
    output        JSONB,
    error         TEXT,
    duration_ms   INT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT tool_results_tool_name_values CHECK (tool_name IN (
        'web_search', 'calculator', 'weather', 'wikipedia',
        'code_execute', 'memory_search', 'memory_store'
    )),
    CONSTRAINT tool_results_duration_positive CHECK (duration_ms IS NULL OR duration_ms >= 0)

);

CREATE INDEX IF NOT EXISTS idx_tool_results_task_id ON tool_results (task_id);
CREATE INDEX IF NOT EXISTS idx_tool_results_tool_name ON tool_results (tool_name);


-- TABLE: embeddings_metadata
-- Stores 384-dim vectors from all-MiniLM-L6-v2 via memory_agent/embeddings.py

CREATE TABLE IF NOT EXISTS embeddings_metadata (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id        UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    task_id       UUID REFERENCES tasks(id) ON DELETE SET NULL,
    content       TEXT NOT NULL,
    embedding     vector(384) NOT NULL,
    model         TEXT NOT NULL DEFAULT 'all-MiniLM-L6-v2',
    metadata      JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT embeddings_content_not_empty CHECK (char_length(trim(content)) > 0),
    CONSTRAINT embeddings_model_values CHECK (model IN ('all-MiniLM-L6-v2'))
);


-- IVFFlat index for approximate nearest-neighbour cosine similarity search
-- lists = 100 is appropriate for up to ~1M vectors; tune upward at scale
-- operator class: vector_cosine_ops matches <=> operator used in pgvector_store.py
CREATE INDEX IF NOT EXISTS idx_embeddings_embedding
    ON embeddings_metadata
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_embeddings_run_id ON embeddings_metadata (run_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_created_at ON embeddings_metadata (created_at DESC);


-- updated_at trigger function (applies to users, runs, tasks)

CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE TRIGGER trg_runs_updated_at
    BEFORE UPDATE ON runs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE TRIGGER trg_tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();