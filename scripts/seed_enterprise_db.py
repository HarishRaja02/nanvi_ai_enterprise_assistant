"""Enterprise Database Seeder and Synchronizer for Local PostgreSQL and Supabase.

Ingests all files and CSV datasets from C:\CompanyData into:
1. Local PostgreSQL (DATABASE_URL)
2. Supabase PostgreSQL (SUPABASE_DATABASE_URL, if configured)
Also outputs deploy/supabase_migration_and_seed.sql for 1-click execution in Supabase Dashboard.
"""
from __future__ import annotations

import csv
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import psycopg
from backend.core.config import Settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_enterprise_db")


CREATE_TABLES_SQL = """
-- 1. Files & Documents Registry
CREATE TABLE IF NOT EXISTS public.files (
    id VARCHAR(120) PRIMARY KEY,
    folder VARCHAR(120) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    relative_path VARCHAR(500) NOT NULL,
    full_path TEXT NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    record_count INTEGER NOT NULL DEFAULT 0,
    summary TEXT,
    created_at VARCHAR(100) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_files_folder ON public.files(folder);
CREATE INDEX IF NOT EXISTS idx_files_filename ON public.files(filename);

-- 2. Transactions & Ledger Records
CREATE TABLE IF NOT EXISTS public.transactions (
    id VARCHAR(120) PRIMARY KEY,
    transaction_id VARCHAR(120) NOT NULL,
    date VARCHAR(50) NOT NULL,
    account_id VARCHAR(120) NOT NULL,
    transaction_type VARCHAR(50) NOT NULL,
    category VARCHAR(120) NOT NULL,
    merchant VARCHAR(255) NOT NULL,
    amount NUMERIC(15, 2) NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'INR',
    status VARCHAR(50) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON public.transactions(transaction_type);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON public.transactions(status);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON public.transactions(date);

-- 3. Customers
CREATE TABLE IF NOT EXISTS public.customers (
    id VARCHAR(120) PRIMARY KEY,
    customer_id VARCHAR(120) NOT NULL,
    name VARCHAR(255) NOT NULL,
    city VARCHAR(100) NOT NULL,
    customer_type VARCHAR(100) NOT NULL,
    industry VARCHAR(100) NOT NULL,
    segment VARCHAR(100) NOT NULL DEFAULT 'Enterprise',
    annual_value NUMERIC(15, 2) NOT NULL DEFAULT 0,
    annual_income NUMERIC(15, 2) NOT NULL DEFAULT 0,
    credit_score INTEGER NOT NULL DEFAULT 700,
    account_status VARCHAR(50) NOT NULL DEFAULT 'Active',
    status VARCHAR(50) NOT NULL DEFAULT 'Active'
);
CREATE INDEX IF NOT EXISTS idx_customers_city ON public.customers(city);
CREATE INDEX IF NOT EXISTS idx_customers_status ON public.customers(status);

-- 4. Contracts
CREATE TABLE IF NOT EXISTS public.contracts (
    id VARCHAR(120) PRIMARY KEY,
    contract_id VARCHAR(120) NOT NULL,
    customer VARCHAR(255) NOT NULL,
    type VARCHAR(100) NOT NULL,
    contract_type VARCHAR(100) NOT NULL,
    party_a VARCHAR(255) NOT NULL,
    party_b VARCHAR(255) NOT NULL,
    start_date VARCHAR(50) NOT NULL,
    end_date VARCHAR(50) NOT NULL,
    annual_value NUMERIC(15, 2) NOT NULL DEFAULT 0,
    value_inr NUMERIC(15, 2) NOT NULL DEFAULT 0,
    renewal_date VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    renewal_notice_days INTEGER NOT NULL DEFAULT 30
);
CREATE INDEX IF NOT EXISTS idx_contracts_status ON public.contracts(status);

-- 5. Projects
CREATE TABLE IF NOT EXISTS public.projects (
    id VARCHAR(120) PRIMARY KEY,
    project_id VARCHAR(120) NOT NULL,
    name VARCHAR(255) NOT NULL,
    owner VARCHAR(120) NOT NULL,
    budget NUMERIC(15, 2) NOT NULL,
    status VARCHAR(50) NOT NULL,
    priority VARCHAR(50) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_status ON public.projects(status);

-- 6. Tasks
CREATE TABLE IF NOT EXISTS public.tasks (
    id VARCHAR(120) PRIMARY KEY,
    task_id VARCHAR(120) NOT NULL,
    project_id VARCHAR(120) NOT NULL,
    task TEXT NOT NULL,
    owner VARCHAR(120) NOT NULL,
    status VARCHAR(50) NOT NULL,
    priority VARCHAR(50) NOT NULL,
    due_date VARCHAR(50) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON public.tasks(project_id);

-- 7. Employees
CREATE TABLE IF NOT EXISTS public.employees (
    id VARCHAR(120) PRIMARY KEY,
    employee_id VARCHAR(120) NOT NULL,
    name VARCHAR(255) NOT NULL,
    department VARCHAR(100) NOT NULL,
    role VARCHAR(150) NOT NULL,
    salary NUMERIC(15, 2) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'Active',
    joined_at VARCHAR(50) NOT NULL DEFAULT '2024-01-01'
);
CREATE INDEX IF NOT EXISTS idx_employees_dept ON public.employees(department);

-- 8. Departments
CREATE TABLE IF NOT EXISTS public.departments (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    budget NUMERIC(15, 2) NOT NULL,
    manager VARCHAR(150) NOT NULL
);

-- 9. Invoices
CREATE TABLE IF NOT EXISTS public.invoices (
    id VARCHAR(120) PRIMARY KEY,
    customer VARCHAR(255) NOT NULL,
    amount NUMERIC(15, 2) NOT NULL,
    status VARCHAR(50) NOT NULL,
    due_date VARCHAR(50) NOT NULL,
    category VARCHAR(100) NOT NULL DEFAULT 'General',
    invoice_date VARCHAR(50) NOT NULL DEFAULT '2026-01-01'
);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON public.invoices(status);
"""


def collect_company_data(root_dir: str = "C:/CompanyData") -> dict[str, list[dict[str, Any]]]:
    root = Path(root_dir)
    data: dict[str, list[dict[str, Any]]] = {
        "files": [],
        "transactions": [],
        "customers": [],
        "contracts": [],
        "projects": [],
        "tasks": [],
        "employees": [],
        "departments": [
            {"id": 1, "name": "Engineering", "budget": 4500000.0, "manager": "David Kim"},
            {"id": 2, "name": "Finance", "budget": 2200000.0, "manager": "Bob Chen"},
            {"id": 3, "name": "HR", "budget": 950000.0, "manager": "Carol Martinez"},
            {"id": 4, "name": "Sales", "budget": 3100000.0, "manager": "Frank Miller"},
            {"id": 5, "name": "Operations", "budget": 1800000.0, "manager": "Henry Ford"},
        ],
        "invoices": [
            {"id": "INV-2026-001", "customer": "Acme Corporation", "amount": 45000.0, "status": "Paid", "due_date": "2026-01-15", "category": "Consulting", "invoice_date": "2026-01-01"},
            {"id": "INV-2026-002", "customer": "Apex Global Systems", "amount": 68000.0, "status": "Pending", "due_date": "2026-02-28", "category": "Subscription", "invoice_date": "2026-01-15"},
            {"id": "INV-2026-003", "customer": "Globex International", "amount": 38000.0, "status": "Overdue", "due_date": "2026-01-30", "category": "Hardware", "invoice_date": "2025-12-15"},
            {"id": "INV-2026-004", "customer": "Initech Solutions", "amount": 12000.0, "status": "Paid", "due_date": "2026-02-10", "category": "Consulting", "invoice_date": "2026-01-10"},
            {"id": "INV-2026-005", "customer": "Hooli Cloud Systems", "amount": 61000.0, "status": "Overdue", "due_date": "2026-02-15", "category": "Cloud Hosting", "invoice_date": "2026-01-05"},
        ],
    }

    if not root.exists():
        logger.warning(f"Root path {root_dir} does not exist.")
        return data

    logger.info(f"Scanning C:/CompanyData for all files and datasets...")

    # 1. Collect all files for public.files registry
    file_idx = 1
    for path in sorted(root.rglob("*")):
        if path.is_file():
            ext = path.suffix.lower()
            rel = path.relative_to(root).as_posix()
            folder = path.parent.name
            top_folder = rel.split("/")[0] if "/" in rel else folder
            size = path.stat().st_size
            summary = f"{top_folder} {ext.lstrip('.').upper()} file: {path.stem.replace('_', ' ')}"
            data["files"].append({
                "id": f"FILE-{file_idx:04d}",
                "folder": top_folder,
                "filename": path.name,
                "relative_path": rel,
                "full_path": str(path).replace("\\", "/"),
                "file_type": ext,
                "size_bytes": size,
                "record_count": 0,
                "summary": summary,
                "created_at": "2026-09-24",
            })
            file_idx += 1

    # 2. Ingest CSV data
    for path in root.rglob("*.csv"):
        folder = path.parent.name
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                
                # Check for transactions
                if folder == "04_Transactions_CSV" or "transaction_id" in (reader.fieldnames or []):
                    for r in rows:
                        data["transactions"].append({
                            "id": r.get("transaction_id", f"TX-{len(data['transactions'])+1}"),
                            "transaction_id": r.get("transaction_id", ""),
                            "date": r.get("date", "2026-01-01"),
                            "account_id": r.get("account_id", ""),
                            "transaction_type": r.get("transaction_type", "Debit"),
                            "category": r.get("category", "General"),
                            "merchant": r.get("merchant", "Vendor"),
                            "amount": float(r.get("amount", 0) or 0),
                            "currency": r.get("currency", "INR"),
                            "status": r.get("status", "Completed"),
                        })

                # Check for customers
                elif folder in ("04_Customer_CSV", "05_Customers_CSV") or "customer_id" in (reader.fieldnames or []):
                    for r in rows:
                        cid = r.get("customer_id", f"CUST-{len(data['customers'])+1}")
                        data["customers"].append({
                            "id": cid,
                            "customer_id": cid,
                            "name": r.get("name", "Unknown Customer"),
                            "city": r.get("city", "Mumbai"),
                            "customer_type": r.get("customer_type", r.get("segment", "Enterprise")),
                            "industry": r.get("industry", "Technology"),
                            "segment": r.get("segment", r.get("customer_type", "Enterprise")),
                            "annual_value": float(r.get("annual_value", r.get("annual_income", 0)) or 0),
                            "annual_income": float(r.get("annual_income", r.get("annual_value", 0)) or 0),
                            "credit_score": int(r.get("credit_score", 700) or 700),
                            "account_status": r.get("account_status", r.get("status", "Active")),
                            "status": r.get("status", r.get("account_status", "Active")),
                        })

                # Check for contracts
                elif folder == "CSV_Contract_Registers" or "contract_id" in (reader.fieldnames or []):
                    for r in rows:
                        cid = r.get("contract_id", f"CTR-{len(data['contracts'])+1}")
                        data["contracts"].append({
                            "id": cid,
                            "contract_id": cid,
                            "customer": r.get("party_b", r.get("party_a", "Acme")),
                            "type": r.get("type", "Standard"),
                            "contract_type": r.get("type", "Standard"),
                            "party_a": r.get("party_a", "Company"),
                            "party_b": r.get("party_b", "Vendor"),
                            "start_date": r.get("start_date", "2026-01-01"),
                            "end_date": r.get("end_date", "2027-01-01"),
                            "annual_value": float(r.get("value_inr", 0) or 0),
                            "value_inr": float(r.get("value_inr", 0) or 0),
                            "renewal_date": r.get("end_date", "2027-01-01"),
                            "status": r.get("status", "Active"),
                            "renewal_notice_days": int(r.get("renewal_notice_days", 30) or 30),
                        })

                # Check for tasks
                elif folder == "05_Tasks_CSV" or "task_id" in (reader.fieldnames or []):
                    for r in rows:
                        tid = r.get("task_id", f"T-{len(data['tasks'])+1}")
                        data["tasks"].append({
                            "id": tid,
                            "task_id": tid,
                            "project_id": r.get("project_id", ""),
                            "task": r.get("task", "Task"),
                            "owner": r.get("owner", "Team"),
                            "status": r.get("status", "Pending"),
                            "priority": r.get("priority", "Medium"),
                            "due_date": r.get("due_date", "2026-12-31"),
                        })

                # Check for projects
                elif folder == "04_Project_CSV" or "project_id" in (reader.fieldnames or []):
                    for r in rows:
                        pid = r.get("project_id", f"P-{len(data['projects'])+1}")
                        data["projects"].append({
                            "id": pid,
                            "project_id": pid,
                            "name": r.get("name", "Project"),
                            "owner": r.get("owner", "Engineering"),
                            "budget": float(r.get("budget", 0) or 0),
                            "status": r.get("status", "In Progress"),
                            "priority": r.get("priority", "Medium"),
                        })

                # Check for employees
                elif folder == "04_Employee_CSV" or "employee_id" in (reader.fieldnames or []):
                    for r in rows:
                        eid = r.get("employee_id", f"E-{len(data['employees'])+1}")
                        data["employees"].append({
                            "id": eid,
                            "employee_id": eid,
                            "name": r.get("name", "Employee"),
                            "department": r.get("department", "Engineering"),
                            "role": r.get("role", "Staff"),
                            "salary": float(r.get("salary", 100000) or 100000),
                            "status": r.get("status", "Active"),
                            "joined_at": "2023-01-01",
                        })

                # Check for vendor payment schedule -> invoices
                elif path.name == "vendor_payment_schedule.csv":
                    for r in rows:
                        inv_id = r.get("Invoice ID", f"INV-{len(data['invoices'])+1}")
                        amt = float(str(r.get("Amount ($)", 0)).replace("$", "").replace(",", "").strip() or 0)
                        data["invoices"].append({
                            "id": inv_id,
                            "customer": r.get("Vendor Name", "Vendor"),
                            "amount": amt,
                            "status": r.get("Payment Status", "Pending"),
                            "due_date": r.get("Due Date", "2026-03-30"),
                            "category": r.get("Category", "Vendor Payment"),
                            "invoice_date": r.get("Invoice Date", "2026-02-28"),
                        })

        except Exception as exc:
            logger.warning(f"Error parsing CSV {path}: {exc}")

    # Remove duplicates from data by id
    for table_name in ("transactions", "customers", "contracts", "projects", "tasks", "employees", "invoices"):
        seen = set()
        deduped = []
        for row in data[table_name]:
            rid = str(row.get("id"))
            if rid not in seen:
                seen.add(rid)
                deduped.append(row)
        data[table_name] = deduped

    logger.info("Collected Records Summary:")
    for tbl, rows in data.items():
        logger.info(f"  {tbl}: {len(rows)} records")

    return data


def seed_database(dsn: str, data: dict[str, list[dict[str, Any]]], name: str = "PostgreSQL") -> None:
    logger.info(f"Connecting to {name}...")
    try:
        conn = psycopg.connect(dsn, autocommit=True)
    except Exception as exc:
        logger.error(f"Could not connect to {name} ({dsn}): {exc}")
        return

    cur = conn.cursor()
    logger.info(f"Applying schema DDL to {name}...")
    cur.execute(CREATE_TABLES_SQL)

    # Insert data table by table
    for table_name, rows in data.items():
        if not rows:
            continue
        first_row = rows[0]
        columns = list(first_row.keys())
        cols_str = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        sql = f"INSERT INTO public.{table_name} ({cols_str}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING"

        batch_values = []
        for r in rows:
            batch_values.append(tuple(r[c] for c in columns))

        cur.executemany(sql, batch_values)
        cur.execute(f"SELECT COUNT(*) FROM public.{table_name}")
        total = cur.fetchone()[0]
        logger.info(f"  [{name}] public.{table_name}: {total} rows present in database.")

    conn.close()
    logger.info(f"Successfully populated all data into {name}!")


def generate_supabase_sql_file(data: dict[str, list[dict[str, Any]]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Generating exportable SQL script: {out_path}...")
    lines = [
        "-- Nanvi AI Enterprise Assistant - Supabase Migration & Seed Script",
        "-- Run this script in your Supabase SQL Editor to populate all enterprise tables and records.",
        "",
        CREATE_TABLES_SQL,
        "",
        "BEGIN;",
    ]

    for table_name, rows in data.items():
        if not rows:
            continue
        lines.append(f"\n-- Seed public.{table_name} ({len(rows)} rows)")
        columns = list(rows[0].keys())
        cols_str = ", ".join(columns)
        for r in rows:
            vals = []
            for c in columns:
                v = r[c]
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                else:
                    escaped = str(v).replace("'", "''")
                    vals.append(f"'{escaped}'")
            lines.append(f"INSERT INTO public.{table_name} ({cols_str}) VALUES ({', '.join(vals)}) ON CONFLICT (id) DO NOTHING;")

    lines.append("\nCOMMIT;")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info(f"Exported Supabase SQL migration script ({len(lines)} lines) to {out_path}")


def main():
    settings = Settings.from_env()
    data = collect_company_data("C:/CompanyData")

    # 1. Local PostgreSQL
    if settings.database_url:
        logger.info(f"\n================ Seeding Local PostgreSQL ================")
        seed_database(settings.database_url, data, name="Local PostgreSQL")
    else:
        logger.warning("DATABASE_URL is not set.")

    # 2. Supabase Cloud PostgreSQL
    supabase_dsn = settings.supabase_database_url or os.getenv("SUPABASE_DATABASE_URL", "")
    if supabase_dsn:
        logger.info(f"\n================ Seeding Supabase Cloud Database ================")
        seed_database(supabase_dsn, data, name="Supabase PostgreSQL")
    else:
        logger.info("\n[Supabase Status] SUPABASE_DATABASE_URL is not yet set in .env.")
        logger.info("When you create your Supabase project, paste its direct connection URI into .env:")
        logger.info("SUPABASE_DATABASE_URL=postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres")

    # 3. Generate 1-click SQL migration for Supabase Dashboard
    sql_file = ROOT / "deploy" / "supabase_migration_and_seed.sql"
    generate_supabase_sql_file(data, sql_file)

    logger.info("\nDatabase initialization complete! Ready for local PostgreSQL and Supabase deployment.")


if __name__ == "__main__":
    main()
