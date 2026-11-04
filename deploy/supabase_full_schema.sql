-- ==============================================================================
-- NANVI AI ENTERPRISE ASSISTANT - MASTER SUPABASE SCHEMA
-- Run this complete script in your Supabase SQL Editor:
-- Dashboard -> Select Project -> SQL Editor -> New Query -> Paste & Run.
-- ==============================================================================

-- Enable common extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ==============================================================================
-- 1. AUTHENTICATION & USER MANAGEMENT
-- ==============================================================================

-- Local accounts for Nanvi login (scrypt password hashed)
CREATE TABLE IF NOT EXISTS public.nanvi_local_accounts (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'enterprise-tenant',
    username TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('Superior', 'Supervisor', 'Project Engineer', 'Employee', 'Admin')),
    display_name TEXT NOT NULL,
    email TEXT,
    department TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, username)
);
CREATE INDEX IF NOT EXISTS idx_nanvi_accounts_email ON public.nanvi_local_accounts(tenant_id, LOWER(email));

-- Password reset tokens
CREATE TABLE IF NOT EXISTS public.nanvi_password_reset_tokens (
    token_hash TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'enterprise-tenant',
    expires_at BIGINT NOT NULL,
    used BOOLEAN NOT NULL DEFAULT FALSE,
    created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nanvi_reset_tokens_acc ON public.nanvi_password_reset_tokens(tenant_id, account_id);

-- ==============================================================================
-- 2. SYSTEM LOGS, AUDIT & AGENT SYNCHRONIZATION
-- ==============================================================================

-- User chat query & answer audit logs
CREATE TABLE IF NOT EXISTS public.user_query_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    user_name TEXT,
    user_role TEXT,
    tenant_id TEXT NOT NULL DEFAULT 'enterprise-tenant',
    query TEXT NOT NULL,
    answer TEXT NOT NULL,
    capability TEXT,
    model TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    log_date VARCHAR(10) NOT NULL DEFAULT TO_CHAR(NOW() AT TIME ZONE 'UTC', 'DD-MM-YYYY')
);
CREATE INDEX IF NOT EXISTS idx_user_query_logs_date ON public.user_query_logs(log_date);
CREATE INDEX IF NOT EXISTS idx_user_query_logs_created_at ON public.user_query_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_query_logs_user ON public.user_query_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_user_query_logs_tenant ON public.user_query_logs(tenant_id);

-- Cloud sync storage for Nanvi Windows Local Agent (BAT agent)
CREATE TABLE IF NOT EXISTS public.nanvi_local_agent_store (
    tenant_id TEXT NOT NULL DEFAULT 'enterprise-tenant',
    user_id TEXT NOT NULL,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, user_id)
);

-- Support and trouble tickets
CREATE TABLE IF NOT EXISTS public.nanvi_support_tickets (
    id TEXT PRIMARY KEY,
    reporter_id TEXT NOT NULL,
    reporter_name TEXT NOT NULL,
    reporter_email TEXT NOT NULL,
    reporter_role TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    subject TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Open',
    admin_notes TEXT,
    diagnostic_info TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_support_tickets_status ON public.nanvi_support_tickets(status);
CREATE INDEX IF NOT EXISTS idx_support_tickets_reporter ON public.nanvi_support_tickets(reporter_id);

-- Executive generated reports (PDF / CSV / XLSX)
CREATE TABLE IF NOT EXISTS public.nanvi_reports (
    report_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    owner_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    format VARCHAR(16) NOT NULL,
    storage_name VARCHAR(255) NOT NULL,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    content_base64 TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    download_token_hash VARCHAR(64),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    downloaded BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_nanvi_reports_owner ON public.nanvi_reports(tenant_id, owner_id);

-- ==============================================================================
-- 3. CONNECTIONS HUB & OAUTH INTEGRATIONS
-- ==============================================================================

-- Third-party provider connections (Gmail, Google Drive, Outlook, Slack, Salesforce, etc.)
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
    services_config JSONB DEFAULT '{}',
    sync_config JSONB DEFAULT '{"auto_sync": true, "frequency": "1h"}',
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

-- OAuth state tokens for PKCE & CSRF protection
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

-- Audit events for connection actions
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

-- Connected mailboxes (Gmail live agent)
CREATE TABLE IF NOT EXISTS public.user_email_accounts (
    id VARCHAR(120) PRIMARY KEY,
    user_id VARCHAR(120) NOT NULL,
    tenant_id VARCHAR(120) NOT NULL DEFAULT 'enterprise-tenant',
    email_address VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    provider VARCHAR(50) NOT NULL DEFAULT 'google',
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at DOUBLE PRECISION,
    scopes TEXT,
    avatar_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    connected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_synced_at TIMESTAMP WITH TIME ZONE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_email_unique ON public.user_email_accounts(user_id, email_address);
CREATE INDEX IF NOT EXISTS idx_user_email_user ON public.user_email_accounts(user_id);

-- ==============================================================================
-- 4. CHAT CONVERSATIONS & SOURCE CITATIONS
-- ==============================================================================

-- Chat conversation sessions
CREATE TABLE IF NOT EXISTS public.conversations (
    conversation_id VARCHAR(128) PRIMARY KEY,
    owner_id VARCHAR(128) NOT NULL,
    tenant_id VARCHAR(128) NOT NULL DEFAULT 'enterprise-tenant',
    title VARCHAR(256),
    active_document VARCHAR(256),
    context JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON public.conversations(tenant_id, owner_id);

-- Messages within conversations
CREATE TABLE IF NOT EXISTS public.conversation_messages (
    id BIGSERIAL PRIMARY KEY,
    conversation_id VARCHAR(128) NOT NULL REFERENCES public.conversations(conversation_id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    data_source VARCHAR(32) DEFAULT 'live',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_conv_messages ON public.conversation_messages(conversation_id, id);

-- Citations, documents references and snippets
CREATE TABLE IF NOT EXISTS public.source_references (
    reference_id VARCHAR(128) PRIMARY KEY,
    source_id VARCHAR(256) NOT NULL,
    source_type VARCHAR(64) NOT NULL,
    owner_id VARCHAR(128) NOT NULL,
    tenant_id VARCHAR(128) NOT NULL DEFAULT 'enterprise-tenant',
    department VARCHAR(128),
    restricted_department VARCHAR(128),
    reference_data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_source_ref_tenant ON public.source_references(tenant_id, source_type);

-- ==============================================================================
-- 5. ENTERPRISE BUSINESS DOMAIN TABLES
-- ==============================================================================

-- Files & Documents Registry
CREATE TABLE IF NOT EXISTS public.files (
    id VARCHAR(120) PRIMARY KEY,
    folder VARCHAR(120) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    relative_path VARCHAR(500) NOT NULL,
    full_path TEXT NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    record_count INTEGER NOT NULL DEFAULT 0,
    summary TEXT,
    created_at VARCHAR(100) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_files_folder ON public.files(folder);
CREATE INDEX IF NOT EXISTS idx_files_filename ON public.files(filename);

-- Financial Transactions & Ledger
CREATE TABLE IF NOT EXISTS public.transactions (
    id VARCHAR(120) PRIMARY KEY,
    transaction_id VARCHAR(120) NOT NULL,
    date VARCHAR(50) NOT NULL,
    account_id VARCHAR(120) NOT NULL,
    transaction_type VARCHAR(50) NOT NULL,
    category VARCHAR(120) NOT NULL,
    merchant VARCHAR(255) NOT NULL,
    amount NUMERIC(15, 2) NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'INR',
    status VARCHAR(50) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON public.transactions(transaction_type);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON public.transactions(status);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON public.transactions(date);

-- Customers Directory
CREATE TABLE IF NOT EXISTS public.customers (
    id VARCHAR(120) PRIMARY KEY,
    customer_id VARCHAR(120) NOT NULL,
    name VARCHAR(255) NOT NULL,
    city VARCHAR(100) NOT NULL,
    customer_type VARCHAR(100) NOT NULL,
    industry VARCHAR(100) NOT NULL,
    segment VARCHAR(100) NOT NULL DEFAULT 'Enterprise',
    annual_value NUMERIC(15, 2) NOT NULL DEFAULT 0,
    annual_income NUMERIC(15, 2) NOT NULL DEFAULT 0,
    credit_score INTEGER NOT NULL DEFAULT 700,
    account_status VARCHAR(50) NOT NULL DEFAULT 'Active',
    status VARCHAR(50) NOT NULL DEFAULT 'Active'
);
CREATE INDEX IF NOT EXISTS idx_customers_city ON public.customers(city);
CREATE INDEX IF NOT EXISTS idx_customers_status ON public.customers(status);

-- Contracts & NDAs
CREATE TABLE IF NOT EXISTS public.contracts (
    id VARCHAR(120) PRIMARY KEY,
    contract_id VARCHAR(120) NOT NULL,
    customer VARCHAR(255) NOT NULL,
    type VARCHAR(100) NOT NULL,
    contract_type VARCHAR(100) NOT NULL,
    party_a VARCHAR(255) NOT NULL,
    party_b VARCHAR(255) NOT NULL,
    start_date VARCHAR(50) NOT NULL,
    end_date VARCHAR(50) NOT NULL,
    annual_value NUMERIC(15, 2) NOT NULL DEFAULT 0,
    value_inr NUMERIC(15, 2) NOT NULL DEFAULT 0,
    renewal_date VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    renewal_notice_days INTEGER NOT NULL DEFAULT 30
);
CREATE INDEX IF NOT EXISTS idx_contracts_status ON public.contracts(status);

-- Projects
CREATE TABLE IF NOT EXISTS public.projects (
    id VARCHAR(120) PRIMARY KEY,
    project_id VARCHAR(120) NOT NULL,
    name VARCHAR(255) NOT NULL,
    owner VARCHAR(120) NOT NULL,
    budget NUMERIC(15, 2) NOT NULL,
    status VARCHAR(50) NOT NULL,
    priority VARCHAR(50) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_status ON public.projects(status);

-- Project Tasks
CREATE TABLE IF NOT EXISTS public.tasks (
    id VARCHAR(120) PRIMARY KEY,
    task_id VARCHAR(120) NOT NULL,
    project_id VARCHAR(120) NOT NULL,
    task TEXT NOT NULL,
    owner VARCHAR(120) NOT NULL,
    status VARCHAR(50) NOT NULL,
    priority VARCHAR(50) NOT NULL,
    due_date VARCHAR(50) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON public.tasks(project_id);

-- Employees & HR
CREATE TABLE IF NOT EXISTS public.employees (
    id VARCHAR(120) PRIMARY KEY,
    employee_id VARCHAR(120) NOT NULL,
    name VARCHAR(255) NOT NULL,
    department VARCHAR(100) NOT NULL,
    role VARCHAR(150) NOT NULL,
    salary NUMERIC(15, 2) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'Active',
    joined_at VARCHAR(50) NOT NULL DEFAULT '2024-01-01'
);
CREATE INDEX IF NOT EXISTS idx_employees_dept ON public.employees(department);

-- Departments
CREATE TABLE IF NOT EXISTS public.departments (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    budget NUMERIC(15, 2) NOT NULL,
    manager VARCHAR(150) NOT NULL
);

-- Invoices & Billing
CREATE TABLE IF NOT EXISTS public.invoices (
    id VARCHAR(120) PRIMARY KEY,
    customer VARCHAR(255) NOT NULL,
    amount NUMERIC(15, 2) NOT NULL,
    status VARCHAR(50) NOT NULL,
    due_date VARCHAR(50) NOT NULL,
    category VARCHAR(100) NOT NULL DEFAULT 'General',
    invoice_date VARCHAR(50) NOT NULL DEFAULT '2026-01-01'
);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON public.invoices(status);

-- ==============================================================================
-- 6. DEFAULT ACCOUNTS BOOTSTRAP (Admin & Demo Users)
-- ==============================================================================

-- Insert default admin user:
-- Username: admin | Password: admin@company | Role: Admin
INSERT INTO public.nanvi_local_accounts (
    id, tenant_id, username, password_salt, password_hash, role, display_name, email, department, active
) VALUES (
    'acc-admin-default',
    'enterprise-tenant',
    'admin',
    'd80b7400a40d5ea66e13b865615d8628',
    '835d259c19b027ca54388e330be4511d73a7d4cf4ee4b859550e50efb06f376f',
    'Admin',
    'System Administrator',
    'admin@company.com',
    'Executive',
    TRUE
) ON CONFLICT (tenant_id, username) DO NOTHING;

-- Insert default CEO (Superior) user:
-- Username: ceo | Password: ceo@nanvi | Role: Superior
INSERT INTO public.nanvi_local_accounts (
    id, tenant_id, username, password_salt, password_hash, role, display_name, email, department, active
) VALUES (
    'acc-ceo-default',
    'enterprise-tenant',
    'ceo',
    'c179c3d97f26f7431e11a37c3746654a',
    '4c0c451da778736a6e76aa49405bb31e5f8f9e61e064ecdb879bbad3e3dcf8ba',
    'Superior',
    'Arjun Mehta',
    'ceo@nanvi.local',
    'Executive',
    TRUE
) ON CONFLICT (tenant_id, username) DO NOTHING;

