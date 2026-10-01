"""Canonical single source of truth for all synthetic enterprise datasets.

Used exclusively across:
1. SQLite development database seeds (backend/integrations/database/sqlite.py)
2. Synthetic test/demo fixtures (backend/integrations/fixtures/synthetic_data.py)
3. Company-data sample generation
4. Frontend demo fallback fixtures (frontend/src/lib/demoFallback.ts)

Every entity has a single canonical representation (e.g. INV-2026-001 has exactly one amount;
Alice Johnson has exactly one role and salary).
"""
from __future__ import annotations

from typing import Any

CANONICAL_EMPLOYEES: list[dict[str, Any]] = [
    {
        "id": 1,
        "employee_id": "EMP-001",
        "name": "Alice Johnson",
        "department": "Engineering",
        "role": "Lead Architect",
        "salary": 185000.0,
        "joined_at": "2022-03-15",
        "status": "Active",
    },
    {
        "id": 2,
        "employee_id": "EMP-002",
        "name": "Bob Chen",
        "department": "Finance",
        "role": "Senior Controller",
        "salary": 145000.0,
        "joined_at": "2021-08-01",
        "status": "Active",
    },
    {
        "id": 3,
        "employee_id": "EMP-003",
        "name": "Carol Martinez",
        "department": "Human Resources",
        "role": "HR Director",
        "salary": 150000.0,
        "joined_at": "2023-01-10",
        "status": "Active",
    },
    {
        "id": 4,
        "employee_id": "EMP-004",
        "name": "David Kim",
        "department": "Engineering",
        "role": "DevOps Architect",
        "salary": 175000.0,
        "joined_at": "2020-11-20",
        "status": "Active",
    },
    {
        "id": 5,
        "employee_id": "EMP-005",
        "name": "Diana Prince",
        "department": "Executive",
        "role": "Chief Executive Officer",
        "salary": 320000.0,
        "joined_at": "2019-06-01",
        "status": "Active",
    },
    {
        "id": 6,
        "employee_id": "EMP-006",
        "name": "Evan Wright",
        "department": "Operations",
        "role": "VP Operations",
        "salary": 175000.0,
        "joined_at": "2021-05-18",
        "status": "Active",
    },
    {
        "id": 7,
        "employee_id": "EMP-007",
        "name": "Frank Miller",
        "department": "Sales",
        "role": "Enterprise Account Executive",
        "salary": 130000.0,
        "joined_at": "2022-09-12",
        "status": "Active",
    },
    {
        "id": 8,
        "employee_id": "EMP-008",
        "name": "Grace Hopper",
        "department": "Engineering",
        "role": "Principal AI Engineer",
        "salary": 195000.0,
        "joined_at": "2021-02-15",
        "status": "Active",
    },
]

CANONICAL_DEPARTMENTS: list[dict[str, Any]] = [
    {"id": 1, "department_id": "DEP-01", "name": "Engineering", "budget": 4500000.0, "manager": "David Kim"},
    {"id": 2, "department_id": "DEP-02", "name": "Finance", "budget": 2200000.0, "manager": "Bob Chen"},
    {"id": 3, "department_id": "DEP-03", "name": "Human Resources", "budget": 950000.0, "manager": "Carol Martinez"},
    {"id": 4, "department_id": "DEP-04", "name": "Executive", "budget": 2500000.0, "manager": "Diana Prince"},
    {"id": 5, "department_id": "DEP-05", "name": "Operations", "budget": 1800000.0, "manager": "Evan Wright"},
    {"id": 6, "department_id": "DEP-06", "name": "Sales", "budget": 3100000.0, "manager": "Frank Miller"},
]

CANONICAL_INVOICES: list[dict[str, Any]] = [
    {
        "id": "INV-2026-001",
        "customer": "Acme Corporation",
        "amount": 120450.0,
        "status": "Paid",
        "due_date": "2026-01-15",
        "category": "Software Licensing",
        "invoice_date": "2025-12-15",
    },
    {
        "id": "INV-2026-002",
        "customer": "Apex Global Systems",
        "amount": 68000.0,
        "status": "Pending",
        "due_date": "2026-02-28",
        "category": "Cloud Infrastructure",
        "invoice_date": "2026-01-28",
    },
    {
        "id": "INV-2026-003",
        "customer": "Globex International",
        "amount": 38000.0,
        "status": "Overdue",
        "due_date": "2026-01-30",
        "category": "Consulting & Support",
        "invoice_date": "2025-12-30",
    },
    {
        "id": "INV-2026-004",
        "customer": "Initech Solutions",
        "amount": 12000.0,
        "status": "Paid",
        "due_date": "2026-02-10",
        "category": "Support Retainer",
        "invoice_date": "2026-01-10",
    },
    {
        "id": "INV-2026-005",
        "customer": "Hooli Cloud Systems",
        "amount": 61000.0,
        "status": "Overdue",
        "due_date": "2026-02-15",
        "category": "Platform Subscription",
        "invoice_date": "2026-01-15",
    },
]

CANONICAL_CONTRACTS: list[dict[str, Any]] = [
    {
        "id": "CNT-2023-01",
        "contract_id": "CNT-2023-01",
        "customer": "Acme Corporation",
        "contract_type": "MSA + Order Form",
        "annual_value": 450000.0,
        "renewal_date": "2029-01-14",
        "status": "Active",
    },
    {
        "id": "CNT-2024-08",
        "contract_id": "CNT-2024-08",
        "customer": "Apex Global Systems",
        "contract_type": "Enterprise License",
        "annual_value": 680000.0,
        "renewal_date": "2027-01-31",
        "status": "Active",
    },
    {
        "id": "CNT-2024-12",
        "contract_id": "CNT-2024-12",
        "customer": "Globex International",
        "contract_type": "MSA",
        "annual_value": 380000.0,
        "renewal_date": "2027-05-31",
        "status": "Active",
    },
    {
        "id": "CNT-2025-03",
        "contract_id": "CNT-2025-03",
        "customer": "Initech Solutions",
        "contract_type": "Subscription",
        "annual_value": 120000.0,
        "renewal_date": "2026-11-09",
        "status": "Active",
    },
    {
        "id": "CNT-2025-07",
        "contract_id": "CNT-2025-07",
        "customer": "Hooli Cloud Systems",
        "contract_type": "Enterprise Tier",
        "annual_value": 610000.0,
        "renewal_date": "2029-02-28",
        "status": "Active",
    },
]

CANONICAL_TRANSACTIONS: list[dict[str, Any]] = [
    {
        "id": "TXN-2026-001",
        "transaction_id": "TXN-2026-001",
        "date": "2026-01-15",
        "account_id": "ACC-101",
        "transaction_type": "Credit",
        "category": "Accounts Receivable",
        "merchant": "Acme Corporation",
        "amount": 120450.0,
        "currency": "USD",
        "status": "Settled",
    },
    {
        "id": "TXN-2026-002",
        "transaction_id": "TXN-2026-002",
        "date": "2026-02-10",
        "account_id": "ACC-101",
        "transaction_type": "Credit",
        "category": "Accounts Receivable",
        "merchant": "Initech Solutions",
        "amount": 12000.0,
        "currency": "USD",
        "status": "Settled",
    },
]
