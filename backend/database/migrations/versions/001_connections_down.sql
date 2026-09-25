-- Down migration: 001_connections_down
DROP TABLE IF EXISTS public.connection_audit_events CASCADE;
DROP TABLE IF EXISTS public.oauth_states CASCADE;
DROP TABLE IF EXISTS public.connections CASCADE;
