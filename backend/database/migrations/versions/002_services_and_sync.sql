-- Up migration: 002_services_and_sync
ALTER TABLE public.connections ADD COLUMN IF NOT EXISTS services_config JSONB DEFAULT '{}';
ALTER TABLE public.connections ADD COLUMN IF NOT EXISTS sync_config JSONB DEFAULT '{"auto_sync": true, "frequency": "1h"}';
