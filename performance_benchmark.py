"""Nanvi performance benchmark harness.

Runs component-level benchmarks against the local prototype. External PostgreSQL,
Redis and production LLM services are intentionally not faked as production
measurements; the report records them as unavailable when those services are absent.
"""
from __future__ import annotations
import concurrent.futures
import io
import json
import os
import statistics
import tempfile
import time
import uuid
from pathlib import Path

import psutil
from openpyxl import Workbook
from docx import Document
from pptx import Presentation
from reportlab.pdfgen import canvas

from backend.agents.security_gateway import SecureToolGateway, ToolContext
from backend.documents.parsers.csv_parser import CSVParser
from backend.documents.parsers.excel import ExcelParser
from backend.documents.parsers.pdf import PDFParser
from backend.documents.parsers.pptx import PPTXParser
from backend.documents.parsers.text import TextParser
from backend.documents.parsers.word import WordParser
from backend.jobs.queue import InMemoryJobQueue
from backend.reports.generators import ExcelReportGenerator, PDFReportGenerator, WordReportGenerator, PowerPointReportGenerator
from backend.reports.models import ReportFormat, ReportRequest
from backend.retrieval.embedding import EmbeddingProvider
from backend.retrieval.keyword import KeywordRetriever
from backend.retrieval.models import AccessControlMetadata, RetrievalRequest, SourceMetadata
from backend.retrieval.reranker import NoOpReranker
from backend.retrieval.service import KnowledgeRetrievalService
from backend.retrieval.vector_store import InMemoryVectorStore
from backend.security.audit import AuditLogger, InMemoryAuditSink
from backend.security.authorization import AuthorizationService, Permission, Resource, UserAttributes
from backend.security.authorization.rbac import Role


class DeterministicEmbedding(EmbeddingProvider):
    def embed(self, text: str) -> list[float]:
        vector = [0.0] * 32
        for token in text.lower().split():
            vector[hash(token) % 32] += 1.0
        return vector


def stats(values: list[float]) -> dict[str, float | int]:
    values = sorted(values)
    idx = lambda p: min(len(values) - 1, int(len(values) * p / 100))
    return {
        "n": len(values),
        "mean_ms": statistics.mean(values) * 1000,
        "p50_ms": values[idx(50)] * 1000,
        "p95_ms": values[idx(95)] * 1000,
        "p99_ms": values[idx(99)] * 1000,
        "max_ms": max(values) * 1000,
    }


def bench(fn, n=20, warm=3):
    for _ in range(warm):
        fn()
    values = []
    for _ in range(n):
        started = time.perf_counter()
        fn()
        values.append(time.perf_counter() - started)
    return stats(values)


def make_xlsx(rows=10000):
    wb = Workbook(); ws = wb.active; ws.title = "Data"
    ws.append(["id", "name", "amount"])
    for i in range(rows):
        ws.append([i, f"Employee {i}", i * 1.5])
    out = io.BytesIO(); wb.save(out); return out.getvalue()


def make_docx(rows=1000):
    doc = Document(); doc.add_heading("Large Document", 1)
    for i in range(rows):
        doc.add_paragraph(f"Employee {i}: project data and business information.")
    out = io.BytesIO(); doc.save(out); return out.getvalue()


def make_pptx(slides=100):
    prs = Presentation()
    for i in range(slides):
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        slide.shapes.title.text = f"Slide {i}"
        box = slide.shapes.add_textbox(1000000, 1500000, 8000000, 3000000)
        box.text_frame.text = "Project data " * 100
    out = io.BytesIO(); prs.save(out); return out.getvalue()


def make_pdf(pages=50):
    out = io.BytesIO(); c = canvas.Canvas(out)
    for i in range(pages):
        c.drawString(50, 800, f"Page {i} " + "project roadmap " * 80)
        c.showPage()
    c.save(); return out.getvalue()


def main():
    results = {"environment": {"postgres_available": False, "redis_available": False, "production_llm_available": False}}
    process = psutil.Process(os.getpid())
    rss_before = process.memory_info().rss

    # API/HTTP surface is intentionally measured by existing tests/TestClient elsewhere;
    # component latency is measured here without requiring a production server.
    from fastapi.testclient import TestClient
    from backend.main import app
    client = TestClient(app)
    results["api_health"] = bench(lambda: client.get("/api/health"), 100)

    # Retrieval corpus: 5,000 chunks, authorized to the same tenant.
    kw = KeywordRetriever(); vectors = InMemoryVectorStore(); emb = DeterministicEmbedding()
    audit = AuditLogger(InMemoryAuditSink()); authz = AuthorizationService()
    retrieval = KnowledgeRetrievalService(emb, vectors, kw, NoOpReranker(), authz, audit)
    access = AccessControlMetadata("t1", department="Engineering")
    for i in range(5000):
        source = SourceMetadata("txt", f"s{i}", f"doc{i}.txt", f"Projects/doc{i}.txt", access=access)
        retrieval.index(f"project atlas roadmap launch milestone employee record number {i}", source)
    user = UserAttributes("u1", "t1", "Engineering", frozenset({Role.EMPLOYEE}))
    query = RetrievalRequest("atlas roadmap milestone", 10, 30)
    results["retrieval_5k"] = bench(lambda: retrieval.retrieve(user, query), 50, 5)

    # Large parsing inputs.
    xlsx, docx, pptx, pdf = make_xlsx(), make_docx(), make_pptx(), make_pdf()
    csv = ("id,name,amount\n" + "\n".join(f"{i},Employee {i},{i*1.5}" for i in range(10000))).encode()
    txt = ("project roadmap " * 10000).encode()
    results["parse_xlsx_10k"] = bench(lambda: ExcelParser().parse_bytes(filename="large.xlsx", relative_path="large.xlsx", data=xlsx), 3, 1)
    results["parse_docx_1k"] = bench(lambda: WordParser().parse_bytes(filename="large.docx", relative_path="large.docx", data=docx), 3, 1)
    results["parse_pptx_100"] = bench(lambda: PPTXParser().parse_bytes(filename="large.pptx", relative_path="large.pptx", data=pptx), 3, 1)
    results["parse_pdf_50"] = bench(lambda: PDFParser().parse_bytes(filename="large.pdf", relative_path="large.pdf", data=pdf), 3, 1)
    results["parse_csv_10k"] = bench(lambda: CSVParser().parse_bytes(filename="large.csv", relative_path="large.csv", data=csv), 3, 1)
    results["parse_txt"] = bench(lambda: TextParser().parse_bytes(filename="large.txt", relative_path="large.txt", data=txt), 10, 2)

    # Report generation.
    rows = [{"id": i, "name": f"Employee {i}", "amount": i * 1.5} for i in range(1000)]
    for fmt, generator in [
        (ReportFormat.EXCEL, ExcelReportGenerator()), (ReportFormat.PDF, PDFReportGenerator()),
        (ReportFormat.WORD, WordReportGenerator()), (ReportFormat.POWERPOINT, PowerPointReportGenerator())]:
        def run(generator=generator, fmt=fmt):
            with tempfile.TemporaryDirectory(prefix="nanvi-perf-") as td:
                generator.generate(ReportRequest(uuid.uuid4().hex, "Performance", fmt, "u1", "t1", rows), Path(td) / f"r.{generator.extension}")
        results[f"report_{fmt.value}_1k"] = bench(run, 3, 1)

    # Database query path: SQL policy/validation + shaping of a bounded 500-row result.
    from backend.integrations.database.models import TablePolicy, QueryRequest, QueryResult
    from backend.integrations.database.sql_validation import ReadOnlySQLValidator, SQLValidationPipeline
    table_policy = TablePolicy(
        allowed_tables=frozenset({("public", "employees")}),
        allowed_columns=frozenset({("public", "employees", c) for c in ("id", "name", "amount")}),
    )
    sql_pipeline = SQLValidationPipeline(ReadOnlySQLValidator(table_policy, require_column_policy=True))
    sql = "SELECT id, name, amount FROM employees ORDER BY id LIMIT 500"
    rows_500 = tuple((i, f"Employee {i}", i * 1.5) for i in range(500))
    def database_read_reference():
        sql_pipeline.validate_read(sql, require_bounded_result=True)
        return QueryResult(("id", "name", "amount"), rows_500, False)
    results["database_query_reference_500_rows"] = bench(database_read_reference, 100, 10)

    # Tool gateway overhead with fresh request context per call (budget semantics preserved).
    gateway = SecureToolGateway(authz, AuditLogger(InMemoryAuditSink()), execution_timeout_seconds=2)
    resource = Resource("r", "knowledge_source", "t1")
    def tool_call():
        ctx = ToolContext(uuid.uuid4().hex, user)
        return gateway.execute(ctx, "knowledge", Permission.FILE_READ, resource, lambda: {"ok": True})
    results["tool_execution"] = bench(tool_call, 50, 5)

    # LLM: no production provider is configured in this environment. Keep a transparent
    # synthetic 50ms network/model placeholder solely to show where model latency dominates.
    results["llm_synthetic_50ms"] = bench(lambda: time.sleep(0.05), 10, 1)

    # Queue: local reference only. Redis is unavailable here.
    queue = InMemoryJobQueue()
    results["inmemory_queue_enqueue"] = bench(lambda: queue.enqueue("test", {"x": 1}), 1000, 10)
    started = time.perf_counter()
    jobs = list(queue.jobs)
    processed = 0
    for _ in jobs:
        processed += 1
    elapsed = time.perf_counter() - started
    results["reference_worker"] = {"jobs": processed, "throughput_jobs_per_sec": processed / elapsed if elapsed else 0.0}

    # Multiple simultaneous users: retrieval workload.
    def retrieve_once(i):
        u = UserAttributes(f"u{i}", "t1", "Engineering", frozenset({Role.EMPLOYEE}))
        return retrieval.retrieve(u, query).hits
    concurrency = {}
    for workers in (1, 10, 25, 50):
        cpu0 = process.cpu_times(); rss0 = process.memory_info().rss; t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            list(executor.map(retrieve_once, range(workers * 10)))
        elapsed = time.perf_counter() - t0
        cpu1 = process.cpu_times(); rss1 = process.memory_info().rss
        concurrency[str(workers)] = {
            "requests": workers * 10, "elapsed_s": elapsed,
            "rps": workers * 10 / elapsed if elapsed else 0,
            "cpu_time_s": (cpu1.user + cpu1.system) - (cpu0.user + cpu0.system),
            "cpu_utilization_of_one_core_pct": (((cpu1.user + cpu1.system) - (cpu0.user + cpu0.system)) / elapsed * 100) if elapsed else 0,
            "rss_delta_mb": (rss1 - rss0) / 1024 / 1024,
        }
    results["concurrency_retrieval"] = concurrency
    rss_after = process.memory_info().rss
    results["memory"] = {"rss_before_mb": rss_before / 1024 / 1024, "rss_after_mb": rss_after / 1024 / 1024,
                          "delta_mb": (rss_after - rss_before) / 1024 / 1024}

    out = Path("performance_results.json")
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(out)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
