from pathlib import Path

import pytest

from backend.integrations.database import (
    DatabaseService,
    DatabaseTool,
    QueryRequest,
    QueryResult,
    ReadOnlySQLValidator,
    SQLValidationError,
    SQLValidationPipeline,
    TablePolicy,
)
from backend.security.audit import AuditLogger, InMemoryAuditSink
from backend.security.authorization import AuthorizationService, Role, UserAttributes
from backend.security.authorization import Permission
from backend.security.authorization.abac import Resource


class FakeRepository:
    def __init__(self):
        self.requests = []

    def execute_read(self, request):
        self.requests.append(request)
        return QueryResult(columns=("id",), rows=((1,),))


def user(role=Role.EMPLOYEE, department="Projects", tenant="tenant-a"):
    return UserAttributes("u1", tenant, department, frozenset({role}))


def make_service(repo=None, tables={("public", "employees")}):
    sink = InMemoryAuditSink()
    service = DatabaseService(
        repo or FakeRepository(),
        AuthorizationService(),
        AuditLogger(sink),
        SQLValidationPipeline(ReadOnlySQLValidator(TablePolicy(frozenset(tables), frozenset({("public", "employees", "id"), ("public", "employees", "name")})), require_column_policy=True)),
        tenant_id="tenant-a",
    )
    return service, sink


def test_select_allowed_and_parameter_is_kept_separate():
    repo = FakeRepository(); service, _ = make_service(repo)
    result = service.execute_read(user(), QueryRequest(
        "SELECT id FROM public.employees WHERE name = %s LIMIT 100", ("Alice",)
    ))
    assert result.rows == ((1,),)
    assert repo.requests[0].parameters == ("Alice",)


def test_insert_update_delete_drop_alter_truncate_create_are_blocked():
    validator = ReadOnlySQLValidator(TablePolicy(frozenset({("public", "employees")})))
    for sql in [
        "INSERT INTO public.employees VALUES (1)",
        "UPDATE public.employees SET name='x'",
        "DELETE FROM public.employees",
        "DROP TABLE public.employees",
        "ALTER TABLE public.employees ADD COLUMN x int",
        "TRUNCATE public.employees",
        "CREATE TABLE public.evil(x int)",
    ]:
        with pytest.raises(SQLValidationError):
            validator.validate(sql)


def test_multi_statement_injection_is_blocked():
    validator = ReadOnlySQLValidator(TablePolicy(frozenset({("public", "employees")})))
    with pytest.raises(SQLValidationError):
        validator.validate("SELECT id FROM public.employees; DROP TABLE public.employees;")


def test_comment_and_string_keywords_do_not_trigger_false_positive_but_structure_still_applies():
    validator = ReadOnlySQLValidator(TablePolicy(frozenset({("public", "employees")})))
    refs = validator.validate("SELECT 'DROP TABLE', id FROM public.employees -- DELETE\n")
    assert refs == [("public", "employees")]


def test_sql_injection_using_parameter_value_is_not_interpolated():
    repo = FakeRepository(); service, _ = make_service(repo)
    attack = "' OR 1=1; DROP TABLE public.employees; --"
    service.execute_read(user(), QueryRequest(
        "SELECT id FROM public.employees WHERE name = %s LIMIT 100", (attack,)
    ))
    assert repo.requests[0].sql.endswith("name = %s LIMIT 100")
    assert repo.requests[0].parameters == (attack,)


def test_disallowed_table_is_blocked():
    service, _ = make_service(tables={("public", "employees")})
    with pytest.raises(SQLValidationError):
        service.execute_read(user(), QueryRequest("SELECT * FROM public.payroll"))


def test_schema_table_policy_is_case_insensitive():
    validator = ReadOnlySQLValidator(TablePolicy(frozenset({("public", "employees")})))
    assert validator.validate("SELECT * FROM PUBLIC.Employees") == [("PUBLIC", "Employees")]


def test_employee_can_use_database_read_permission():
    service, _ = make_service()
    assert service.execute_read(user(), QueryRequest("SELECT id FROM public.employees LIMIT 100")).rows


def test_user_without_database_permission_is_denied_before_repository_call():
    class NoDBRepo(FakeRepository):
        def execute_read(self, request):
            raise AssertionError("repository must not be called")
    service, sink = make_service(NoDBRepo())
    # Unknown role is represented by no roles, so RBAC grants nothing.
    denied = UserAttributes("u1", "tenant-a", "Projects", frozenset())
    from backend.integrations.database.exceptions import DatabaseAccessDenied
    with pytest.raises(DatabaseAccessDenied):
        service.execute_read(denied, QueryRequest("SELECT id FROM public.employees LIMIT 100"))
    assert sink.events[-1].outcome == "deny"


def test_cross_tenant_user_is_denied():
    service, sink = make_service()
    foreign = user(tenant="tenant-b")
    from backend.integrations.database.exceptions import DatabaseAccessDenied
    with pytest.raises(DatabaseAccessDenied):
        service.execute_read(foreign, QueryRequest("SELECT id FROM public.employees LIMIT 100"))
    assert sink.events[-1].outcome == "deny"


def test_every_successful_database_access_is_audited():
    service, sink = make_service()
    service.execute_read(user(), QueryRequest("SELECT id FROM public.employees LIMIT 100"))
    event = sink.events[-1]
    assert event.event_type == "database_access"
    assert event.outcome == "allow"
    assert event.metadata["tables"] == ["public.employees"]


def test_database_tool_does_not_expose_repository_or_credentials():
    service, _ = make_service()
    tool = DatabaseTool(service)
    assert tool.read(user(), "SELECT id FROM public.employees LIMIT 100").rows == ((1,),)
    assert not hasattr(tool, "dsn")
    assert not hasattr(tool, "connection")
