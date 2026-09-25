from __future__ import annotations

import sqlite3
import threading
from typing import Any

from .abstraction import DatabaseRepository
from .models import QueryRequest, QueryResult, TablePolicy


ENTERPRISE_TABLES = frozenset({
    ("public", "employees"),
    ("public", "departments"),
    ("public", "invoices"),
    ("public", "contracts"),
    ("public", "transactions"),
    ("public", "customers"),
    ("public", "projects"),
    ("public", "tasks"),
    ("public", "files"),
})

ENTERPRISE_COLUMNS = frozenset({
    # Employees
    ("public", "employees", "id"),
    ("public", "employees", "employee_id"),
    ("public", "employees", "name"),
    ("public", "employees", "department"),
    ("public", "employees", "role"),
    ("public", "employees", "salary"),
    ("public", "employees", "status"),
    ("public", "employees", "joined_at"),
    # Departments
    ("public", "departments", "id"),
    ("public", "departments", "name"),
    ("public", "departments", "budget"),
    ("public", "departments", "manager"),
    # Invoices
    ("public", "invoices", "id"),
    ("public", "invoices", "customer"),
    ("public", "invoices", "amount"),
    ("public", "invoices", "status"),
    ("public", "invoices", "due_date"),
    ("public", "invoices", "category"),
    ("public", "invoices", "invoice_date"),
    # Contracts
    ("public", "contracts", "id"),
    ("public", "contracts", "contract_id"),
    ("public", "contracts", "customer"),
    ("public", "contracts", "type"),
    ("public", "contracts", "contract_type"),
    ("public", "contracts", "party_a"),
    ("public", "contracts", "party_b"),
    ("public", "contracts", "start_date"),
    ("public", "contracts", "end_date"),
    ("public", "contracts", "annual_value"),
    ("public", "contracts", "value_inr"),
    ("public", "contracts", "renewal_date"),
    ("public", "contracts", "status"),
    ("public", "contracts", "renewal_notice_days"),
    # Transactions (Ledger records)
    ("public", "transactions", "id"),
    ("public", "transactions", "transaction_id"),
    ("public", "transactions", "date"),
    ("public", "transactions", "account_id"),
    ("public", "transactions", "transaction_type"),
    ("public", "transactions", "category"),
    ("public", "transactions", "merchant"),
    ("public", "transactions", "amount"),
    ("public", "transactions", "currency"),
    ("public", "transactions", "status"),
    # Customers
    ("public", "customers", "id"),
    ("public", "customers", "customer_id"),
    ("public", "customers", "name"),
    ("public", "customers", "city"),
    ("public", "customers", "customer_type"),
    ("public", "customers", "industry"),
    ("public", "customers", "segment"),
    ("public", "customers", "annual_value"),
    ("public", "customers", "annual_income"),
    ("public", "customers", "credit_score"),
    ("public", "customers", "account_status"),
    ("public", "customers", "status"),
    # Projects
    ("public", "projects", "id"),
    ("public", "projects", "project_id"),
    ("public", "projects", "name"),
    ("public", "projects", "owner"),
    ("public", "projects", "budget"),
    ("public", "projects", "status"),
    ("public", "projects", "priority"),
    # Tasks
    ("public", "tasks", "id"),
    ("public", "tasks", "task_id"),
    ("public", "tasks", "project_id"),
    ("public", "tasks", "task"),
    ("public", "tasks", "owner"),
    ("public", "tasks", "status"),
    ("public", "tasks", "priority"),
    ("public", "tasks", "due_date"),
    # Files & Documents registry
    ("public", "files", "id"),
    ("public", "files", "folder"),
    ("public", "files", "filename"),
    ("public", "files", "relative_path"),
    ("public", "files", "full_path"),
    ("public", "files", "file_type"),
    ("public", "files", "size_bytes"),
    ("public", "files", "record_count"),
    ("public", "files", "summary"),
    ("public", "files", "created_at"),
})

ENTERPRISE_TABLE_POLICY = TablePolicy(
    allowed_tables=ENTERPRISE_TABLES,
    allowed_columns=ENTERPRISE_COLUMNS,
)


class SQLiteEnterpriseRepository(DatabaseRepository):
    """Local SQLite repository for enterprise data when PostgreSQL is not configured."""

    def __init__(self, db_path: str = ":memory:", max_rows: int = 500) -> None:
        self._max_rows = max_rows
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_schema_and_data()

    def _init_schema_and_data(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("ATTACH ':memory:' AS public")

            # Employees table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.employees (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    department TEXT NOT NULL,
                    role TEXT NOT NULL,
                    salary REAL NOT NULL,
                    joined_at TEXT NOT NULL
                )
            """)
            # Also in main schema for unqualified queries
            cur.execute("""
                CREATE TABLE IF NOT EXISTS main.employees (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    department TEXT NOT NULL,
                    role TEXT NOT NULL,
                    salary REAL NOT NULL,
                    joined_at TEXT NOT NULL
                )
            """)

            # Departments table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.departments (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    budget REAL NOT NULL,
                    manager TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS main.departments (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    budget REAL NOT NULL,
                    manager TEXT NOT NULL
                )
            """)

            # Invoices table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.invoices (
                    id TEXT PRIMARY KEY,
                    customer TEXT NOT NULL,
                    amount REAL NOT NULL,
                    status TEXT NOT NULL,
                    due_date TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS main.invoices (
                    id TEXT PRIMARY KEY,
                    customer TEXT NOT NULL,
                    amount REAL NOT NULL,
                    status TEXT NOT NULL,
                    due_date TEXT NOT NULL
                )
            """)

            # Contracts table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.contracts (
                    id TEXT PRIMARY KEY,
                    customer TEXT NOT NULL,
                    contract_type TEXT NOT NULL,
                    annual_value REAL NOT NULL,
                    renewal_date TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS main.contracts (
                    id TEXT PRIMARY KEY,
                    customer TEXT NOT NULL,
                    contract_type TEXT NOT NULL,
                    annual_value REAL NOT NULL,
                    renewal_date TEXT NOT NULL
                )
            """)

            # Seed data
            cur.execute("SELECT COUNT(*) FROM public.employees")
            if cur.fetchone()[0] == 0:
                employees = [
                    (1, "Alice Johnson", "Engineering", "Senior Lead Engineer", 165000.0, "2022-03-15"),
                    (2, "Bob Chen", "Finance", "Senior Financial Analyst", 140000.0, "2021-08-01"),
                    (3, "Carol Martinez", "HR", "HR Business Partner", 115000.0, "2023-01-10"),
                    (4, "David Kim", "Engineering", "DevOps Architect", 175000.0, "2020-11-20"),
                    (5, "Emma Watson", "Executive", "Chief Executive Officer", 350000.0, "2019-06-01"),
                    (6, "Frank Miller", "Sales", "Enterprise Account Executive", 130000.0, "2022-09-12"),
                    (7, "Grace Hopper", "Engineering", "Principal AI Engineer", 195000.0, "2021-05-18"),
                    (8, "Henry Ford", "Operations", "Logistics Director", 125000.0, "2023-04-01"),
                ]
                for table in ("public.employees", "main.employees"):
                    cur.executemany(f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?)", employees)

                departments = [
                    (1, "Engineering", 4500000.0, "David Kim"),
                    (2, "Finance", 2200000.0, "Bob Chen"),
                    (3, "HR", 950000.0, "Carol Martinez"),
                    (4, "Sales", 3100000.0, "Frank Miller"),
                    (5, "Operations", 1800000.0, "Henry Ford"),
                ]
                for table in ("public.departments", "main.departments"):
                    cur.executemany(f"INSERT INTO {table} VALUES (?, ?, ?, ?)", departments)

                invoices = [
                    ("INV-2026-001", "Acme Corporation", 45000.0, "Paid", "2026-01-15"),
                    ("INV-2026-002", "Apex Global Systems", 68000.0, "Pending", "2026-02-28"),
                    ("INV-2026-003", "Globex International", 38000.0, "Overdue", "2026-01-30"),
                    ("INV-2026-004", "Initech Solutions", 12000.0, "Paid", "2026-02-10"),
                    ("INV-2026-005", "Hooli Cloud Systems", 61000.0, "Overdue", "2026-02-15"),
                ]
                for table in ("public.invoices", "main.invoices"):
                    cur.executemany(f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?)", invoices)

                contracts = [
                    ("CNT-2023-01", "Acme Corporation", "MSA + Order Form", 450000.0, "2029-01-14"),
                    ("CNT-2024-08", "Apex Global Systems", "Enterprise License", 680000.0, "2027-01-31"),
                    ("CNT-2024-12", "Globex International", "MSA", 380000.0, "2027-05-31"),
                    ("CNT-2025-03", "Initech Solutions", "Subscription", 120000.0, "2026-11-09"),
                    ("CNT-2025-07", "Hooli Cloud Systems", "Enterprise Tier", 610000.0, "2029-02-28"),
                ]
                for table in ("public.contracts", "main.contracts"):
                    cur.executemany(f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?)", contracts)

            # Transactions table
            for tbl in ("public.transactions", "main.transactions"):
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {tbl} (
                        id TEXT PRIMARY KEY,
                        transaction_id TEXT NOT NULL,
                        date TEXT NOT NULL,
                        account_id TEXT NOT NULL,
                        transaction_type TEXT NOT NULL,
                        category TEXT NOT NULL,
                        merchant TEXT NOT NULL,
                        amount REAL NOT NULL,
                        currency TEXT NOT NULL,
                        status TEXT NOT NULL
                    )
                """)
            cur.execute("SELECT COUNT(*) FROM public.transactions")
            if cur.fetchone()[0] == 0:
                tx_samples = [
                    ("TX-01-0000", "TX-01-0000", "2026-07-19", "ACC-4122", "Debit", "Consulting", "CloudNova", 14549.73, "INR", "Pending"),
                    ("TX-01-0001", "TX-01-0001", "2026-07-20", "ACC-3041", "Credit", "Subscription", "Apex Systems", 85000.0, "INR", "Completed"),
                    ("TX-01-0002", "TX-01-0002", "2026-07-21", "ACC-9182", "Debit", "Hardware", "Dell Enterprise", 125000.0, "INR", "Completed"),
                    ("TX-01-0003", "TX-01-0003", "2026-07-22", "ACC-1049", "Credit", "Software License", "Hooli Cloud", 450000.0, "INR", "Completed"),
                    ("TX-01-0004", "TX-01-0004", "2026-07-23", "ACC-5521", "Debit", "Cloud Hosting", "Amazon Web Services", 68500.0, "INR", "Completed"),
                ]
                for table in ("public.transactions", "main.transactions"):
                    cur.executemany(f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tx_samples)

            # Customers table
            for tbl in ("public.customers", "main.customers"):
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {tbl} (
                        id TEXT PRIMARY KEY,
                        customer_id TEXT NOT NULL,
                        name TEXT NOT NULL,
                        city TEXT NOT NULL,
                        customer_type TEXT NOT NULL,
                        industry TEXT NOT NULL,
                        segment TEXT NOT NULL,
                        annual_value REAL NOT NULL,
                        annual_income REAL NOT NULL,
                        credit_score INTEGER NOT NULL,
                        account_status TEXT NOT NULL,
                        status TEXT NOT NULL
                    )
                """)
            cur.execute("SELECT COUNT(*) FROM public.customers")
            if cur.fetchone()[0] == 0:
                cust_samples = [
                    ("CUST-1000", "CUST-1000", "Acme Corporation", "Pune", "Corporate", "Finance", "Enterprise", 4500000.0, 3514325.0, 750, "Active", "Active"),
                    ("CUST-1001", "CUST-1001", "Apex Global Systems", "Hyderabad", "Enterprise", "Technology", "Enterprise", 6800000.0, 4602837.0, 810, "Active", "Active"),
                    ("CUST-1002", "CUST-1002", "Globex International", "Mumbai", "SMB", "Logistics", "SMB", 3800000.0, 2977503.0, 690, "Active", "Active"),
                    ("CUST-1003", "CUST-1003", "Initech Solutions", "Bengaluru", "Corporate", "Healthcare", "Enterprise", 1200000.0, 1850000.0, 720, "Active", "Active"),
                ]
                for table in ("public.customers", "main.customers"):
                    cur.executemany(f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", cust_samples)

            # Projects table
            for tbl in ("public.projects", "main.projects"):
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {tbl} (
                        id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL,
                        name TEXT NOT NULL,
                        owner TEXT NOT NULL,
                        budget REAL NOT NULL,
                        status TEXT NOT NULL,
                        priority TEXT NOT NULL
                    )
                """)
            cur.execute("SELECT COUNT(*) FROM public.projects")
            if cur.fetchone()[0] == 0:
                proj_samples = [
                    ("P-001-000", "P-001-000", "Data Platform Modernization", "Product", 16861074.0, "In Progress", "High"),
                    ("P-001-001", "P-001-001", "AI Assistant Enterprise Rollout", "Engineering", 12500000.0, "In Progress", "Critical"),
                    ("P-001-002", "P-001-002", "Security & RBAC Enforcement", "DevOps", 4500000.0, "Completed", "High"),
                ]
                for table in ("public.projects", "main.projects"):
                    cur.executemany(f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?)", proj_samples)

            # Tasks table
            for tbl in ("public.tasks", "main.tasks"):
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {tbl} (
                        id TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        project_id TEXT NOT NULL,
                        task TEXT NOT NULL,
                        owner TEXT NOT NULL,
                        status TEXT NOT NULL,
                        priority TEXT NOT NULL,
                        due_date TEXT NOT NULL
                    )
                """)
            cur.execute("SELECT COUNT(*) FROM public.tasks")
            if cur.fetchone()[0] == 0:
                task_samples = [
                    ("T-001-000", "T-001-000", "P-001-000", "Documentation & Architecture Sign-off", "Backend", "Completed", "High", "2026-12-24"),
                    ("T-001-001", "T-001-001", "P-001-001", "Supabase & Postgres Multi-DB Sync", "Data Team", "In Progress", "Critical", "2026-10-15"),
                ]
                for table in ("public.tasks", "main.tasks"):
                    cur.executemany(f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?, ?)", task_samples)

            # Files table
            for tbl in ("public.files", "main.files"):
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {tbl} (
                        id TEXT PRIMARY KEY,
                        folder TEXT NOT NULL,
                        filename TEXT NOT NULL,
                        relative_path TEXT NOT NULL,
                        full_path TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL,
                        record_count INTEGER NOT NULL,
                        summary TEXT,
                        created_at TEXT NOT NULL
                    )
                """)
            cur.execute("SELECT COUNT(*) FROM public.files")
            if cur.fetchone()[0] == 0:
                file_samples = [
                    ("F-001", "Finance", "transactions_01.csv", "Finance/04_Transactions_CSV/transactions_01.csv", "C:/CompanyData/Finance/04_Transactions_CSV/transactions_01.csv", ".csv", 154200, 100, "Financial transactions and ledger records", "2026-09-24"),
                    ("F-002", "Finance", "q1_2026_financial_summary.xlsx", "Finance/q1_2026_financial_summary.xlsx", "C:/CompanyData/Finance/q1_2026_financial_summary.xlsx", ".xlsx", 245000, 0, "Q1 financial summary breakdown workbook", "2026-09-24"),
                    ("F-003", "HR", "employee_handbook_2026.pdf", "HR/employee_handbook_2026.pdf", "C:/CompanyData/HR/employee_handbook_2026.pdf", ".pdf", 524000, 0, "Enterprise employee policy handbook", "2026-09-24"),
                    ("F-004", "Contracts", "contract_register_01.csv", "Contracts/CSV_Contract_Registers/contract_register_01.csv", "C:/CompanyData/Contracts/CSV_Contract_Registers/contract_register_01.csv", ".csv", 89400, 100, "Enterprise contract register and renewal dates", "2026-09-24"),
                ]
                for table in ("public.files", "main.files"):
                    cur.executemany(f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", file_samples)

            self._conn.commit()

    def execute_read(self, request: QueryRequest) -> QueryResult:
        with self._lock:
            cur = self._conn.cursor()
            # PostgreSQL uses %s, SQLite uses ?
            sql = request.sql.replace("%s", "?")
            cur.execute(sql, request.parameters)
            columns = tuple(d[0] for d in cur.description) if cur.description else ()
            rows = cur.fetchmany(self._max_rows)
            truncated = len(rows) == self._max_rows
            return QueryResult(columns=columns, rows=tuple(tuple(r) for r in rows), truncated=truncated)

    def close(self) -> None:
        with self._lock:
            self._conn.close()
