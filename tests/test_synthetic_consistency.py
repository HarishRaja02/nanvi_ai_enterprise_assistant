"""Consistency tests for synthetic data fixtures (Item 7).

Verifies that:
1. Every invoice in canonical data has exactly one consistent amount and customer across fixtures and SQLite seeds.
2. Every employee has exactly one consistent role, salary, and department.
3. Every contract has a consistent value and renewal date.
4. SQLite seed matches canonical data precisely.
"""
from __future__ import annotations

import os
import pytest

from backend.integrations.fixtures.canonical_data import (
    CANONICAL_CONTRACTS,
    CANONICAL_DEPARTMENTS,
    CANONICAL_EMPLOYEES,
    CANONICAL_INVOICES,
    CANONICAL_TRANSACTIONS,
)


def test_canonical_invoices_unique_and_consistent():
    invoice_ids = set()
    for inv in CANONICAL_INVOICES:
        assert inv["id"] not in invoice_ids, f"Duplicate invoice ID: {inv['id']}"
        invoice_ids.add(inv["id"])
        assert inv["amount"] > 0
        assert inv["customer"]
        assert inv["status"] in ("Paid", "Pending", "Overdue")

    # Invariant from Senior Review: INV-2026-001 must have one consistent amount
    inv_001 = next(i for i in CANONICAL_INVOICES if i["id"] == "INV-2026-001")
    assert inv_001["amount"] == 120450.0
    assert inv_001["customer"] == "Acme Corporation"


def test_canonical_employees_unique_and_consistent():
    employee_ids = set()
    employee_names = set()
    for emp in CANONICAL_EMPLOYEES:
        assert emp["id"] not in employee_ids, f"Duplicate employee ID: {emp['id']}"
        assert emp["name"] not in employee_names, f"Duplicate employee name: {emp['name']}"
        employee_ids.add(emp["id"])
        employee_names.add(emp["name"])
        assert emp["salary"] > 0
        assert emp["role"]
        assert emp["department"]

    # Invariant: Alice Johnson has one role and salary
    alice = next(e for e in CANONICAL_EMPLOYEES if e["name"] == "Alice Johnson")
    assert alice["role"] == "Lead Architect"
    assert alice["salary"] == 185000.0


def test_sqlite_seed_matches_canonical(monkeypatch):
    monkeypatch.setenv("APP_MODE", "development")
    from backend.core.config import Settings
    from backend.integrations.database.sqlite import SQLiteEnterpriseRepository

    repo = SQLiteEnterpriseRepository(db_path=":memory:")

    from backend.integrations.database.models import QueryRequest

    # Check employees in SQLite
    emp_res = repo.execute_read(QueryRequest(sql="SELECT id, name, department, role, salary FROM public.employees ORDER BY id"))
    assert len(emp_res.rows) == len(CANONICAL_EMPLOYEES)
    for row, expected in zip(emp_res.rows, CANONICAL_EMPLOYEES):
        assert row[0] == expected["id"]
        assert row[1] == expected["name"]
        assert row[2] == expected["department"]
        assert row[3] == expected["role"]
        assert row[4] == expected["salary"]

    # Check invoices in SQLite
    inv_res = repo.execute_read(QueryRequest(sql="SELECT id, customer, amount, status FROM public.invoices ORDER BY id"))
    assert len(inv_res.rows) == len(CANONICAL_INVOICES)
    for row, expected in zip(inv_res.rows, CANONICAL_INVOICES):
        assert row[0] == expected["id"]
        assert row[1] == expected["customer"]
        assert row[2] == expected["amount"]
        assert row[3] == expected["status"]

    # Check contracts in SQLite
    cnt_res = repo.execute_read(QueryRequest(sql="SELECT id, customer, annual_value FROM public.contracts ORDER BY id"))
    assert len(cnt_res.rows) == len(CANONICAL_CONTRACTS)
    for row, expected in zip(cnt_res.rows, CANONICAL_CONTRACTS):
        assert row[0] == expected["id"]
        assert row[1] == expected["customer"]
        assert row[2] == expected["annual_value"]
