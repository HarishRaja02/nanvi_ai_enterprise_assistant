-- Up migration: 001_connections
CREATE TABLE IF NOT EXISTS public.connections (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(120) NOT NULL,
    owner_user_id VARCHAR(120),
    scope_level VARCHAR(20) NOT NULL DEFAULT 'user' CHECK (scope_level IN ('user', 'organization')),
    provider VARCHAR(100) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    account_identifier VARCHAR(255),
    credential_type VARCHAR(50) NOT NULL,
    encrypted_credentials BYTEA,
    encryption_key_id VARCHAR(50),
    granted_scopes TEXT[],
    metadata_safe JSONB DEFAULT '{}',
    status VARCHAR(30) NOT NULL DEFAULT 'DISCONNECTED',
    status_reason VARCHAR(100),
    last_tested_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    last_synced_at TIMESTAMPTZ,
    created_by VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS uix_connections_unique
    ON public.connections (tenant_id, provider, account_identifier, scope_level, COALESCE(owner_user_id, ''))
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_connections_tenant_status
    ON public.connections (tenant_id, status) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS public.oauth_states (
    state VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(120) NOT NULL,
    tenant_id VARCHAR(120) NOT NULL,
    provider VARCHAR(100) NOT NULL,
    pkce_verifier VARCHAR(128),
    redirect_after VARCHAR(500),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_oauth_states_expires ON public.oauth_states (expires_at);

CREATE TABLE IF NOT EXISTS public.connection_audit_events (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(120) NOT NULL,
    actor_user_id VARCHAR(120),
    connection_id VARCHAR(64),
    provider VARCHAR(100),
    event VARCHAR(60) NOT NULL,
    safe_metadata JSONB DEFAULT '{}',
    ip VARCHAR(45),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conn_audit_tenant ON public.connection_audit_events (tenant_id, created_at DESC);
