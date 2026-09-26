CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    protocol TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    title TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    protocol TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    tool_calls JSONB NOT NULL DEFAULT '[]',
    metadata JSONB NOT NULL DEFAULT '{}',
    embedding vector(768)
);

CREATE TABLE IF NOT EXISTS facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    active BOOLEAN NOT NULL DEFAULT true,
    metadata JSONB NOT NULL DEFAULT '{}',
    UNIQUE (category, key)
);

CREATE TABLE IF NOT EXISTS task_log (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    protocol TEXT NOT NULL DEFAULT 'shadow',
    executor_id TEXT,
    budget_cap NUMERIC,
    spend NUMERIC NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    result TEXT,
    error TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_embedding ON messages USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_facts_category_key ON facts(category, key);
CREATE INDEX IF NOT EXISTS idx_task_log_status ON task_log(status);
ALTER TABLE task_log ADD COLUMN IF NOT EXISTS business_id TEXT;
-- sticky flag: true the moment a task ever passes through GATED, never reset — this is
-- what PRD §8's "% of missions completed without human intervention" actually measures.
ALTER TABLE task_log ADD COLUMN IF NOT EXISTS was_gated BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS idx_task_log_business ON task_log(business_id);

-- ── P3 · Projects / Tasks persistence ────────────────────────────────
-- Mirrors the shape of src/data.ts's PROJECTS / TASKS_TODAY / TASKS_UPCOMING mocks
-- closely enough that the frontend swap is a data-source change, not a markup change.
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Ongoing',
    priority TEXT NOT NULL DEFAULT 'Medium',
    due_date DATE,
    people JSONB NOT NULL DEFAULT '[]',
    agents_note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    meta TEXT NOT NULL DEFAULT '',
    when_bucket TEXT NOT NULL DEFAULT 'today',   -- 'today' | 'upcoming'
    status TEXT NOT NULL DEFAULT 'open',         -- 'open' | 'done' | 'blocked'
    delegated_task_id TEXT,                      -- set once handed to Anthony (shadow task_log.id)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_when_bucket ON tasks(when_bucket);

-- ── P6 · Guard configuration ──────────────────────────────────────────
-- Singleton row (id is always 1) so caps/rules are editable from Settings without
-- touching .env or restarting the server. shadow/guard_config.py owns reads/writes.
CREATE TABLE IF NOT EXISTS guard_config (
    id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    daily_budget NUMERIC NOT NULL DEFAULT 5.00,
    per_task_budget_default NUMERIC NOT NULL DEFAULT 0.50,
    high_cost_multiplier NUMERIC NOT NULL DEFAULT 2.0,
    long_running_minutes INT NOT NULL DEFAULT 30,
    custom_rules JSONB NOT NULL DEFAULT '[]',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── P5 · File / URL ingest (first hook of the Phase 6 Archive) ────────
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,     -- 'upload' | 'url'
    title TEXT NOT NULL,
    origin TEXT NOT NULL,     -- filename or URL
    content TEXT NOT NULL,
    char_count INT NOT NULL DEFAULT 0,
    embedding vector(768),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS business_id TEXT;
CREATE INDEX IF NOT EXISTS idx_documents_business ON documents(business_id);

CREATE INDEX IF NOT EXISTS idx_documents_embedding ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ── Phase 4 · Auth + Business (docs/PHASE_3_4_PLAN.md §1) ──────────────
-- Off by default (DEXTER_REQUIRE_AUTH=false) — when off, everything attributes to an
-- auto-created "default" business/user, same bootstrap-on-first-use pattern as
-- Prometheus's own first-workspace bootstrap. Sessions are opaque bearer tokens,
-- hashed at rest (same shape as Prometheus's mcpTokens: never store the plaintext).
CREATE TABLE IF NOT EXISTS businesses (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS business_members (
    business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member', -- 'owner' | 'admin' | 'member'
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (business_id, user_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
-- Which of the user's (possibly several) businesses this session currently acts as;
-- set at login/register, changeable via POST /api/auth/switch-business.
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS current_business_id TEXT;
-- Pending invites: hash of the one-time code `register` must present to claim the
-- placeholder account (knowing the email alone isn't enough). NULL once claimed.
ALTER TABLE users ADD COLUMN IF NOT EXISTS invite_code_hash TEXT;

CREATE INDEX IF NOT EXISTS idx_business_members_user ON business_members(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

-- Nullable: existing local rows (pre-auth) aren't orphaned by this migration.
ALTER TABLE projects ADD COLUMN IF NOT EXISTS business_id TEXT REFERENCES businesses(id);
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS business_id TEXT REFERENCES businesses(id);
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS user_id TEXT;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS business_id TEXT;
CREATE INDEX IF NOT EXISTS idx_projects_business ON projects(business_id);
CREATE INDEX IF NOT EXISTS idx_tasks_business ON tasks(business_id);
CREATE INDEX IF NOT EXISTS idx_conversations_business ON conversations(business_id);

-- ── Phase 4 · Persistent Agent identity (docs/PHASE_3_4_PLAN.md §2) ────
-- Every ExecutorManager.spawn() writes a row here and updates it on completion —
-- before this, an executor was a pure in-memory object with no identity or history.
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'executor',  -- 'orchestrated' | 'executor'
    model_route TEXT,
    status TEXT NOT NULL DEFAULT 'queued',  -- mirrors TaskStatus
    efficiency_score REAL,
    budget_cap NUMERIC,
    spend NUMERIC NOT NULL DEFAULT 0,
    owner_user_id TEXT REFERENCES users(id),
    business_id TEXT REFERENCES businesses(id),
    task_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_agents_business ON agents(business_id);
CREATE INDEX IF NOT EXISTS idx_agents_task ON agents(task_id);

-- ── Dependency map (PRD §4's `Dependency` object: business↔team↔agent↔tool) ────
-- Real agent→tool edges — one row per tool call an executor actually made, so the
-- Dependency map (docs/PHASE_3_4_PLAN.md §7) shows what happened, not a guess. Written
-- best-effort from tools/registry.py; missing rows just mean "not observed yet," never
-- a fabricated edge.
CREATE TABLE IF NOT EXISTS agent_tool_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    success BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agent_tool_calls_task ON agent_tool_calls(task_id);

-- ── Credit ledger (PRD §5.5) ──────────────────────────────────────────
-- Every model call's cost, persisted (the in-memory trackers reset on restart, so a monthly
-- budget or per-provider cap was impossible). ledger.py owns reads/writes.
CREATE TABLE IF NOT EXISTS spend_ledger (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    business_id TEXT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    cost_usd NUMERIC NOT NULL DEFAULT 0,
    task_id TEXT,
    agent_id TEXT,
    source TEXT NOT NULL DEFAULT 'executor'   -- 'executor' | 'chat' | 'briefing' | 'archive'
);
CREATE INDEX IF NOT EXISTS idx_spend_ledger_business_ts ON spend_ledger(business_id, ts);
ALTER TABLE guard_config ADD COLUMN IF NOT EXISTS limits JSONB NOT NULL DEFAULT '{}';

-- ── Home headline stats (PRD §5.2) ─────────────────────────────────────
-- Optional per-task attribution the Commander gives when delegating; revenue and hours are
-- only ever summed from these, never invented.
ALTER TABLE task_log ADD COLUMN IF NOT EXISTS minutes_saved INT;
ALTER TABLE task_log ADD COLUMN IF NOT EXISTS revenue_value NUMERIC;
ALTER TABLE task_log ADD COLUMN IF NOT EXISTS model_route TEXT;

-- ── Archive v1 (Phase 6) ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notebooks (
    id TEXT PRIMARY KEY,
    business_id TEXT,
    title TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS notebook_id TEXT;

-- ── Full pass · spawn templates, presence (server/ops.py) ─────────────
CREATE TABLE IF NOT EXISTS spawn_templates (
    id TEXT PRIMARY KEY,
    business_id TEXT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    tier INTEGER,
    budget_cap NUMERIC,
    minutes_saved INTEGER,
    priority TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_spawn_templates_business ON spawn_templates(business_id);
-- Team presence: bumped (at most once a minute) whenever a session makes an authenticated call.
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;
