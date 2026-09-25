# RBAC

## Implemented roles

- CEO
- Finance
- HR
- Manager
- Employee
- IT Admin

`ROLE_PERMISSIONS` defines coarse-grained permission grants. RBAC answers whether a role grants a permission; it does not decide tenant/resource/department constraints.

## Permission highlights

| Role | Broad access represented in code |
|---|---|
| CEO | File/email/database read+write, reports, Finance, HR, audit |
| Finance | File/email/database read+write, reports, Finance |
| HR | File/email read+write, database read, reports, HR |
| Manager | File/email read+write, database read, reports |
| Employee | File/email/database read, reports |
| IT Admin | File/email/database read+write, audit, report download |

These are code-level grants; ABAC can still deny a request.

## Partially implemented

Roles are derived from token claims only for the role values recognized by the enum. There is no admin UI or role-management API in this repository.

## Planned/Future

Role lifecycle/assignment remains an identity-provider or enterprise administration concern and is not implemented by Nanvi.
