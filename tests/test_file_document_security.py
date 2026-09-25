from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import pytest
from backend.integrations.files import ConfiguredLocalFileRepository, FileService, InvalidFilePath, FileTypeNotAllowed, FileTooLarge, FileAccessDenied
from backend.security.audit import AuditLogger, InMemoryAuditSink
from backend.security.authorization import AuthorizationService, UserAttributes, Role
from backend.documents import DocumentProcessingService, PDFParser, WordParser, ExcelParser, CSVParser, PPTXParser, TextParser, DocumentProcessingError

ROOT_NAMES = ("Customers", "Finance", "HR", "Projects", "Contracts")

def user(role=Role.EMPLOYEE, dept="Projects"):
    return UserAttributes("u1", "t1", dept, frozenset({role}))

def make_env(tmp_path):
    roots={n: tmp_path/n for n in ROOT_NAMES}
    for p in roots.values(): p.mkdir()
    (roots["Projects"] / "roadmap.txt").write_text("Atlas", encoding="utf-8")
    return roots

def make_service(roots, max_size=10*1024*1024):
    repo=ConfiguredLocalFileRepository(roots, max_file_size_bytes=max_size)
    sink=InMemoryAuditSink(); return FileService(repo, AuthorizationService(), AuditLogger(sink)), sink

def test_exactly_configured_company_roots_and_virtual_paths(tmp_path):
    roots=make_env(tmp_path); svc,_=make_service(roots)
    assert [x.relative_path for x in svc.list_files(user(), "Projects")] == ["projects/roadmap.txt"]
    with pytest.raises(InvalidFilePath): svc.get_metadata(user(), "Other/secret.txt")

def test_traversal_absolute_unc_and_drive_paths_are_blocked(tmp_path):
    roots=make_env(tmp_path); repo=ConfiguredLocalFileRepository(roots)
    for value in ["../../etc/passwd","Projects/../../HR/x.txt","/etc/passwd","\\HR\\x.txt","C:\\CompanyData\\HR\\x.txt","C:/CompanyData/HR/x.txt","\\\\server\\share\\x.txt"]:
        with pytest.raises(InvalidFilePath): repo.get_metadata(value)

def test_symlink_escape_is_blocked(tmp_path):
    roots=make_env(tmp_path); outside=tmp_path/"outside.txt"; outside.write_text("secret")
    link=roots["Projects"] / "escape.txt"
    try: link.symlink_to(outside)
    except (OSError, NotImplementedError): pytest.skip("symlinks unavailable")
    repo=ConfiguredLocalFileRepository(roots)
    with pytest.raises(InvalidFilePath): repo.get_metadata("Projects/escape.txt")

def test_malicious_filename_does_not_escape(tmp_path):
    roots=make_env(tmp_path); (roots["Projects"] / "..\\evil.txt").write_text("x")
    svc,_=make_service(roots)
    with pytest.raises(InvalidFilePath): svc.get_metadata(user(), "Projects/..\\evil.txt")

def test_size_and_extension_limits(tmp_path):
    roots=make_env(tmp_path); (roots["Projects"] / "large.txt").write_bytes(b"123456")
    (roots["Projects"] / "bad.exe").write_bytes(b"MZ")
    repo=ConfiguredLocalFileRepository(roots,max_file_size_bytes=5)
    with pytest.raises(FileTooLarge): repo.get_metadata("Projects/large.txt")
    with pytest.raises(FileTypeNotAllowed): repo.get_metadata("Projects/bad.exe")

def test_permission_filtering(tmp_path):
    roots=make_env(tmp_path); (roots["HR"] / "salary.txt").write_text("secret")
    svc,_=make_service(roots)
    with pytest.raises(FileAccessDenied): svc.read_file(user(), "HR/salary.txt")
    assert svc.read_file(user(Role.HR,"HR"), "HR/salary.txt") == b"secret"

def test_document_pipeline_only_accepts_bytes_and_preserves_safe_source():
    svc=DocumentProcessingService([PDFParser(),WordParser(),ExcelParser(),CSVParser(),PPTXParser(),TextParser()])
    doc=svc.parse_bytes(filename="Projects/a.txt",relative_path="Projects/a.txt",data=b"hello")
    assert doc.source.path=="Projects/a.txt"
    assert not hasattr(svc, "parse")

def test_controlled_file_service_is_only_filesystem_processing_entry(tmp_path):
    roots=make_env(tmp_path); fs,_=make_service(roots)
    (roots["Projects"] / "a.txt").write_text("hello")
    dps=DocumentProcessingService([TextParser()])
    doc=dps.parse_file(fs,user(),"Projects/a.txt")
    assert doc.text=="hello" and doc.source.path=="projects/a.txt"

def test_malformed_documents_are_safely_rejected():
    dps=DocumentProcessingService([WordParser(),ExcelParser(),PPTXParser(),PDFParser(),TextParser()])
    for name in ["bad.docx","bad.xlsx","bad.pptx","bad.pdf"]:
        with pytest.raises(DocumentProcessingError): dps.parse_bytes(filename=name,relative_path=name,data=b"not-a-real-document")

def test_ooxml_archive_bomb_limits():
    data=b"A"*(1024*1024)
    import io
    buf=io.BytesIO()
    with ZipFile(buf,"w",ZIP_DEFLATED) as z: z.writestr("word/document.xml",data)
    with pytest.raises(DocumentProcessingError): DocumentProcessingService([WordParser()]).parse_bytes(filename="x.docx",relative_path="x.docx",data=buf.getvalue())

def test_unsupported_zip_archive_rejected():
    dps=DocumentProcessingService([TextParser()])
    with pytest.raises(Exception): dps.parse_bytes(filename="payload.zip",relative_path="payload.zip",data=b"PK")
