-- ============================================================
-- LEAPXO SKILL ENGINE v2.1 – Production Database Schema
-- Target: PostgreSQL 15+
-- ============================================================

-- Enable pgcrypto for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ------------------------------------------------------------
-- Skill Registry
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS skills (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id      TEXT        UNIQUE NOT NULL,
    version       TEXT        NOT NULL DEFAULT '1.0.0',
    intent        TEXT        NOT NULL,
    output_format TEXT        NOT NULL CHECK (output_format IN ('text', 'json', 'markdown')),
    region_code   TEXT        NOT NULL DEFAULT 'GLOBAL',
    security_level TEXT       NOT NULL DEFAULT 'standard'
                              CHECK (security_level IN ('standard', 'high', 'critical')),
    signature     TEXT,
    public_key    TEXT,
    created_at    TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_skills_region   ON skills (region_code);
CREATE INDEX IF NOT EXISTS idx_skills_security ON skills (security_level);

-- ------------------------------------------------------------
-- Skill Dependencies (DAG edges)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS skill_dependencies (
    id         UUID  PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id   TEXT  NOT NULL REFERENCES skills (skill_id) ON DELETE CASCADE,
    depends_on TEXT  NOT NULL REFERENCES skills (skill_id) ON DELETE CASCADE,
    UNIQUE (skill_id, depends_on)
);

-- ------------------------------------------------------------
-- Approval Logs (Governance)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS approvals (
    id         UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id   TEXT      NOT NULL REFERENCES skills (skill_id) ON DELETE CASCADE,
    approver_id TEXT     NOT NULL,
    status     TEXT      NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
    risk_level TEXT      NOT NULL DEFAULT 'low'
                         CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    notes      TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_approvals_skill  ON approvals (skill_id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals (status);

-- ------------------------------------------------------------
-- Audit Trail (Immutable – append-only)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id         UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
    action     TEXT      NOT NULL,
    actor      TEXT      NOT NULL,
    metadata   JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_actor  ON audit_logs (actor);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs (action);
CREATE INDEX IF NOT EXISTS idx_audit_ts     ON audit_logs (created_at DESC);

-- Prevent updates and deletes on audit_logs (immutability guard)
CREATE OR REPLACE FUNCTION audit_logs_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_logs is append-only: UPDATE and DELETE are not allowed';
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_no_update ON audit_logs;
CREATE TRIGGER trg_audit_no_update
  BEFORE UPDATE OR DELETE ON audit_logs
  FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable();

-- ------------------------------------------------------------
-- Skill Execution Log
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS execution_logs (
    id           UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id     TEXT      NOT NULL,
    prompt_hash  TEXT      NOT NULL,
    latency_ms   INTEGER,
    safety_score NUMERIC(5, 4),
    status       TEXT      NOT NULL CHECK (status IN ('success', 'blocked', 'error')),
    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_exec_skill  ON execution_logs (skill_id);
CREATE INDEX IF NOT EXISTS idx_exec_status ON execution_logs (status);
CREATE INDEX IF NOT EXISTS idx_exec_ts     ON execution_logs (created_at DESC);

-- ------------------------------------------------------------
-- Semantic Cache (metadata table; actual cache lives in Redis)
-- Records what is cached so the cache can be warmed on restart.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS semantic_cache (
    prompt_hash TEXT      PRIMARY KEY,
    skill_id    TEXT      NOT NULL,
    response    TEXT      NOT NULL,
    cached_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMP NOT NULL DEFAULT NOW() + INTERVAL '1 hour'
);

CREATE INDEX IF NOT EXISTS idx_cache_expires ON semantic_cache (expires_at);
