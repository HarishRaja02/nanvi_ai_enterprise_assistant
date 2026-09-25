from __future__ import annotations

from pathlib import Path

import pytest

from backend.integrations.files import (
    FileAccessDenied,
    FileTooLarge,
    FileTypeNotAllowed,
    InvalidFilePath,
    LocalFileRepository,
    FileService,
)
from backend.security.audit import AuditLogger, InMemoryAuditSink
from backend.security.authorization import Role, AuthorizationService, UserAttributes


TENANT = "tenant-a"


def make_user(user_id: str, department: str, role: Role = Role.EMPLOYEE) -> UserAttributes:
    return UserAttributes(
        user_id=user_id,
        tenant_id=TENANT,
        department=department,
        roles=frozenset({role}),
    )


@pytest.fixture
def company_root(tmp_path: Path) -> Path:
    (tmp_path / "Projects").mkdir()
    (tmp_path / "HR").mkdir()
    (tmp_path / "Finance").mkdir()
    (tmp_path / "Projects" / "roadmap.txt").write_text("project roadmap", encoding="utf-8")
    (tmp_path / "Projects" / "budget.csv").write_text("item,cost\nserver,100", encoding="utf-8")
    (tmp_path / "HR" / "salary.txt").write_text("confidential", encoding="utf-8")
    (tmp_path / "Finance" / "forecast.csv").write_text("year,revenue\n2026,100", encoding="utf-8")
    return tmp_path


def make_service(root: Path, *, max_size: int = 10 * 1024 * 1024):
    sink = InMemoryAuditSink()
    repo = LocalFileRepository(root, max_file_size_bytes=max_size)
    service = FileService(repo, AuthorizationService(), AuditLogger(sink))
    return service, sink


def test_file_listing_and_filename_search(company_root: Path) -> None:
    service, _ = make_service(company_root)
    employee = make_user("emp-1", "Engineering")

    files = service.list_files(employee, "Projects")
    assert {item.name for item in files} == {"roadmap.txt", "budget.csv"}

    results = service.search_by_filename(employee, "road", "Projects")
    assert [item.relative_path for item in results] == ["Projects/roadmap.txt"]


def test_metadata_and_read_are_authorized_and_audited(company_root: Path) -> None:
    service, sink = make_service(company_root)
    employee = make_user("emp-1", "Engineering")

    metadata = service.get_metadata(employee, "Projects/roadmap.txt")
    assert metadata.size_bytes == len("project roadmap")
    assert service.read_file(employee, "Projects/roadmap.txt") == b"project roadmap"

    assert [event.outcome for event in sink.events] == ["allow", "allow"]
    assert all(event.event_type == "file_access" for event in sink.events)


def test_employee_can_read_projects_but_hr_salary_is_denied(company_root: Path) -> None:
    service, sink = make_service(company_root)
    employee = make_user("emp-1", "Engineering")

    assert service.read_file(employee, "Projects/roadmap.txt") == b"project roadmap"
    with pytest.raises(FileAccessDenied):
        service.read_file(employee, "HR/salary.txt")

    assert sink.events[-1].outcome == "deny"
    assert sink.events[-1].metadata["reason"] == "Resource policy denied access"


def test_hr_can_read_hr_files_but_not_finance(company_root: Path) -> None:
    service, _ = make_service(company_root)
    hr = make_user("hr-1", "HR", Role.HR)

    assert service.read_file(hr, "HR/salary.txt") == b"confidential"
    with pytest.raises(FileAccessDenied):
        service.read_file(hr, "Finance/forecast.csv")


def test_privileged_role_can_read_restricted_file(company_root: Path) -> None:
    service, _ = make_service(company_root)
    ceo = make_user("ceo-1", "Executive", Role.CEO)
    assert service.read_file(ceo, "HR/salary.txt") == b"confidential"


def test_path_traversal_and_absolute_paths_are_rejected(company_root: Path) -> None:
    repo = LocalFileRepository(company_root)
    bad_paths = [
        "../../etc/passwd",
        "Projects/../../HR/salary.txt",
        "C:\\CompanyData\\HR\\salary.txt",
        "C:/CompanyData/HR/salary.txt",
        "\\\\server\\share\\salary.txt",
        "/etc/passwd",
        "\\HR\\salary.txt",
    ]
    for path in bad_paths:
        with pytest.raises(InvalidFilePath):
            repo.get_metadata(path)


def test_symlink_escape_is_rejected(company_root: Path, tmp_path: Path) -> None:
    outside = company_root.parent / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = company_root / "Projects" / "escape.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symlink creation unavailable: {exc}")

    repo = LocalFileRepository(company_root)
    with pytest.raises(InvalidFilePath):
        repo.get_metadata("Projects/escape.txt")


def test_extension_allowlist_and_size_limit(company_root: Path) -> None:
    (company_root / "Projects" / "script.exe").write_bytes(b"MZ")
    (company_root / "Projects" / "large.txt").write_bytes(b"123456")
    repo = LocalFileRepository(company_root, max_file_size_bytes=5)

    with pytest.raises(FileTypeNotAllowed):
        repo.get_metadata("Projects/script.exe")
    with pytest.raises(FileTooLarge):
        repo.get_metadata("Projects/large.txt")


def test_repository_never_exposes_absolute_path_in_service_api(company_root: Path) -> None:
    service, _ = make_service(company_root)
    employee = make_user("emp-1", "Engineering")
    metadata = service.get_metadata(employee, "Projects/roadmap.txt")
    assert not metadata.relative_path.startswith("/")
    assert "Projects/roadmap.txt" == metadata.relative_path
