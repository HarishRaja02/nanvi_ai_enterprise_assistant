INSERT INTO public.nanvi_local_accounts (
    id, tenant_id, username, password_salt, password_hash, role, display_name, email, department, active
) VALUES (
    'acc-admin-default', 'enterprise-tenant', 'admin', '0d6b2f901eb61c7a4a842b14b82c04bf', '034967a00e36f161c48ee853d85ab3db303490f5a72436709bb3509330d0df6b', 'Admin', 'System Administrator', 'admin@company.com', 'Executive', TRUE
) ON CONFLICT (tenant_id, username) DO UPDATE SET
    password_salt = EXCLUDED.password_salt,
    password_hash = EXCLUDED.password_hash,
    role = EXCLUDED.role,
    active = TRUE;

INSERT INTO public.nanvi_local_accounts (
    id, tenant_id, username, password_salt, password_hash, role, display_name, email, department, active
) VALUES (
    'acc-ceo-default', 'enterprise-tenant', 'ceo', '570c6c8a7aafd7534becff8ad7129a91', 'bf56b8694a610f25b299b2aef131b7354937a9acdaa330c25552e00e15ae39c6', 'Superior', 'Arjun Mehta', 'ceo@nanvi.local', 'Executive', TRUE
) ON CONFLICT (tenant_id, username) DO UPDATE SET
    password_salt = EXCLUDED.password_salt,
    password_hash = EXCLUDED.password_hash,
    role = EXCLUDED.role,
    active = TRUE;

INSERT INTO public.nanvi_local_accounts (
    id, tenant_id, username, password_salt, password_hash, role, display_name, email, department, active
) VALUES (
    'acc-finance-default', 'enterprise-tenant', 'finance', '75e5d2c7d62cc2f340cb8756d193046a', 'f887b1f4f3d1fc6bcc2526143d2c59da985dcf5eb4acf37bfa1db674a44796aa', 'Supervisor', 'Priya Sharma', 'finance@nanvi.local', 'Finance', TRUE
) ON CONFLICT (tenant_id, username) DO UPDATE SET
    password_salt = EXCLUDED.password_salt,
    password_hash = EXCLUDED.password_hash,
    role = EXCLUDED.role,
    active = TRUE;

INSERT INTO public.nanvi_local_accounts (
    id, tenant_id, username, password_salt, password_hash, role, display_name, email, department, active
) VALUES (
    'acc-manager-default', 'enterprise-tenant', 'manager', '1d3e2527ce56b62cb6f066837ab7a95e', '2d2175c2a89d51c76a66c8c5ea2237f2045b989b0af980008b1869f3951e4ac2', 'Supervisor', 'Rahul Patel', 'manager@nanvi.local', 'Operations', TRUE
) ON CONFLICT (tenant_id, username) DO UPDATE SET
    password_salt = EXCLUDED.password_salt,
    password_hash = EXCLUDED.password_hash,
    role = EXCLUDED.role,
    active = TRUE;

INSERT INTO public.nanvi_local_accounts (
    id, tenant_id, username, password_salt, password_hash, role, display_name, email, department, active
) VALUES (
    'acc-engineer-default', 'enterprise-tenant', 'engineer', '92524fc35537a20aa5cddc95be62a676', '522692e27f1821d4ab0a9d82306b9ce7d3137c341f3ad0a44960984ff6052efc', 'Project Engineer', 'Maya Nair', 'engineer@nanvi.local', 'Engineering', TRUE
) ON CONFLICT (tenant_id, username) DO UPDATE SET
    password_salt = EXCLUDED.password_salt,
    password_hash = EXCLUDED.password_hash,
    role = EXCLUDED.role,
    active = TRUE;

INSERT INTO public.nanvi_local_accounts (
    id, tenant_id, username, password_salt, password_hash, role, display_name, email, department, active
) VALUES (
    'acc-hr-default', 'enterprise-tenant', 'hr', '4d7f566dafca20e18c8c2eb6e632dc9a', 'b1976e1108a121ad042896d9bf7033f475235a7d2de693b0dacc94e81071f2ec', 'Project Engineer', 'Kavita Reddy', 'hr@nanvi.local', 'Human Resources', TRUE
) ON CONFLICT (tenant_id, username) DO UPDATE SET
    password_salt = EXCLUDED.password_salt,
    password_hash = EXCLUDED.password_hash,
    role = EXCLUDED.role,
    active = TRUE;

INSERT INTO public.nanvi_local_accounts (
    id, tenant_id, username, password_salt, password_hash, role, display_name, email, department, active
) VALUES (
    'acc-employee-default', 'enterprise-tenant', 'employee', '9be8a0a8e80df4de3fe127e83e242a40', '83e0acd88d9b85f4a6af1c086674b4e633ee0dad93af42d74612b1941b2e8c16', 'Employee', 'Ankit Singh', 'employee@nanvi.local', 'Operations', TRUE
) ON CONFLICT (tenant_id, username) DO UPDATE SET
    password_salt = EXCLUDED.password_salt,
    password_hash = EXCLUDED.password_hash,
    role = EXCLUDED.role,
    active = TRUE;