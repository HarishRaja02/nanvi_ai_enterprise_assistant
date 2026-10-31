-- Down migration: 002_services_and_sync_down
ALTER TABLE public.connections DROP COLUMN IF EXISTS services_config;
ALTER TABLE public.connections DROP COLUMN IF EXISTS sync_config;
