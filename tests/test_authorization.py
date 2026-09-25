import pytest

from backend.security.authorization import (
    AuthorizationService,
    Permission,
    Resource,
    Role,
    UserAttributes,
)


TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


def user(
    user_id: str,
    department: str,
    role: Role,
    tenant_id: str = TENANT_A,
) -> UserAttributes:
    return UserAttributes(
        user_id=user_id,
        tenant_id=tenant_id,
        department=department,
        roles=frozenset({role}),
    )


def resource(
    resource_id: str,
    resource_type: str = "document",
    department: str | None = None,
    tenant_id: str = TENANT_A,
    owner_id: str | None = None,
) -> Resource:
    return Resource(
        resource_id=resource_id,
        resource_type=resource_type,
        tenant_id=tenant_id,
        department=department,
        owner_id=owner_id,
    )


@pytest.fixture
def service() -> AuthorizationService:
    return AuthorizationService()


def test_employee_denied_hr_salary_information(service: AuthorizationService) -> None:
    decision = service.authorize(
        user("emp-1", "Engineering", Role.EMPLOYEE),
        Permission.HR_READ,
        resource("salary-1", department="HR"),
    )

    assert decision.allowed is False


def test_finance_allowed_financial_information(service: AuthorizationService) -> None:
    decision = service.authorize(
        user("fin-1", "Finance", Role.FINANCE),
        Permission.FINANCE_READ,
        resource("financial-1", department="Finance"),
    )

    assert decision.allowed is True


def test_finance_denied_hr_information(service: AuthorizationService) -> None:
    decision = service.authorize(
        user("fin-1", "Finance", Role.FINANCE),
        Permission.HR_READ,
        resource("employee-salary-1", department="HR"),
    )

    assert decision.allowed is False


def test_read_and_write_are_separate(service: AuthorizationService) -> None:
    employee = user("emp-1", "Engineering", Role.EMPLOYEE)

    read_decision = service.authorize(
        employee,
        Permission.FILE_READ,
        resource("shared-file"),
    )
    write_decision = service.authorize(
        employee,
        Permission.FILE_WRITE,
        resource("shared-file"),
    )

    assert read_decision.allowed is True
    assert write_decision.allowed is False


def test_resource_level_ownership(service: AuthorizationService) -> None:
    employee = user("emp-1", "Engineering", Role.EMPLOYEE)

    own = service.authorize(
        employee,
        Permission.FILE_READ,
        resource(
            "private-file",
            resource_type="user_file",
            owner_id="emp-1",
        ),
    )
    other = service.authorize(
        employee,
        Permission.FILE_READ,
        resource(
            "private-file-2",
            resource_type="user_file",
            owner_id="emp-2",
        ),
    )

    assert own.allowed is True
    assert other.allowed is False


def test_tenant_isolation(service: AuthorizationService) -> None:
    decision = service.authorize(
        user("emp-1", "Engineering", Role.EMPLOYEE, tenant_id=TENANT_A),
        Permission.FILE_READ,
        resource("tenant-b-file", tenant_id=TENANT_B),
    )

    assert decision.allowed is False
    assert "Tenant" in decision.reason


def test_missing_role_is_denied(service: AuthorizationService) -> None:
    decision = service.authorize(
        UserAttributes(
            user_id="u-1",
            tenant_id=TENANT_A,
            department="Finance",
            roles=frozenset(),
        ),
        Permission.FINANCE_READ,
        resource("financial-1", department="Finance"),
    )

    assert decision.allowed is False


def test_unknown_permission_is_rejected(service: AuthorizationService) -> None:
    with pytest.raises(ValueError):
        service.authorize(
            user("fin-1", "Finance", Role.FINANCE),
            "NOT_A_PERMISSION",
            resource("financial-1", department="Finance"),
        )
