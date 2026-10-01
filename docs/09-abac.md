# ABAC

## Implemented attributes

`UserAttributes`: user ID, tenant ID, department, roles.

`Resource`: resource ID, resource type, tenant ID, owner ID, department and arbitrary policy attributes.

## Rules

- Cross-tenant access is denied.
- No-role users are denied.
- Finance/HR permission checks use department constraints.
- `user_file` and `user_report` resources are owner-restricted.
- Resources carrying `restricted_department` require matching department unless the user has CEO or IT Admin role.
- ABAC is evaluated after RBAC.

## Security property

The LLM/router does not supply authorization decisions. It can select a capability, but resource access still reaches the central policy service.

## Partially implemented

Some integrations encode department/resource attributes explicitly; richer enterprise attributes are not modeled. There is no policy-management API.

## Planned/Future

Additional enterprise attributes can be added to `Resource.attributes` and evaluated centrally without moving authorization into the AI layer.
