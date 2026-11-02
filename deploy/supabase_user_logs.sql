-- ==============================================================================
-- Nanvi AI Enterprise Assistant — User Query & System Answer Logs Migration
-- Run this script in your Supabase SQL Editor.
-- ==============================================================================

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
    -- Formatted as DD-MM-YYYY (e.g. 02-11-2026) for fast daily grouping and dropdown partitioning
    log_date VARCHAR(10) NOT NULL DEFAULT TO_CHAR(NOW() AT TIME ZONE 'UTC', 'DD-MM-YYYY')
);

-- Indexes for lightning fast daily queries and user sorting
CREATE INDEX IF NOT EXISTS idx_user_query_logs_date ON public.user_query_logs(log_date);
CREATE INDEX IF NOT EXISTS idx_user_query_logs_created_at ON public.user_query_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_query_logs_user ON public.user_query_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_user_query_logs_tenant ON public.user_query_logs(tenant_id);

-- Enable Row Level Security (RLS)
ALTER TABLE public.user_query_logs ENABLE ROW LEVEL SECURITY;

-- Allow service role full read/write access
CREATE POLICY "Allow service role full access on user_query_logs"
    ON public.user_query_logs
    FOR ALL
    USING (true)
    WITH CHECK (true);

COMMENT ON TABLE public.user_query_logs IS 'Audit log of all user chat queries and system-generated answers split by day.';
