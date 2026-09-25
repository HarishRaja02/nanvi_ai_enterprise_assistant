from __future__ import annotations

import re
from backend.security.authorization import UserAttributes


class DefaultDatabaseQueryPlanner:
    """Safe, deterministic SQL query planner that formulates parameterized read-only queries."""

    def plan(self, question: str, user: UserAttributes) -> tuple[str, tuple]:
        text = question.strip()
        lower = text.casefold()

        # 1. If user directly typed a SELECT or WITH query
        if lower.startswith("select ") or lower.startswith("with "):
            sql = text.rstrip(";")
            if "limit" not in lower:
                sql = f"{sql} LIMIT 25"
            return (sql, ())

        # 2. File / Document registry queries (e.g. "search for the file", "find files in db", "get mutual nda from database")
        file_keywords = ("file", "files", "document", "documents", "workbook", "spreadsheet", "resume", "pdf", "docx", "xlsx", "nda", "agreement", "contract", "report", "template")
        search_verbs = ("search", "find", "get", "fetch", "retrieve", "db", "database", "data base", "where", "list", "show", "all", "which", "look", "check", "from database", "from db", "from the database", "from the db", "in database", "in db", "in the database", "in the db")
        if any(w in lower for w in file_keywords) and any(w in lower for w in search_verbs):
            # Check for specific folder filter
            for folder in ("Finance", "Customers", "Contracts", "Projects", "HR", "Resumes", "Uploads"):
                if folder.casefold() in lower:
                    return ("SELECT id, folder, filename, relative_path, file_type, size_bytes FROM public.files WHERE folder = %s LIMIT 25", (folder,))

            # 2a. Mutual NDA / NDA queries - prevent false positives matching 'attendance' or 'standard'
            if "mutual" in lower and "nda" in lower:
                return (
                    "SELECT id, folder, filename, relative_path, file_type, size_bytes FROM public.files WHERE filename LIKE %s OR filename LIKE %s OR summary LIKE %s LIMIT 25",
                    ("%mutual%nda%", "%mutual_nda%", "%mutual%nda%")
                )
            if "mutual" in lower:
                return (
                    "SELECT id, folder, filename, relative_path, file_type, size_bytes FROM public.files WHERE filename LIKE %s OR summary LIKE %s LIMIT 25",
                    ("%mutual%", "%mutual%")
                )
            if re.search(r'\bnda\b', lower):
                return (
                    "SELECT id, folder, filename, relative_path, file_type, size_bytes FROM public.files WHERE filename LIKE %s OR filename LIKE %s OR filename LIKE %s OR filename LIKE %s OR summary LIKE %s LIMIT 25",
                    ("%_nda_%", "%-nda-%", "%_nda.%", "nda_%", "%non-disclosure%")
                )

            # 2b. Check for specific filename search word or extension
            file_match = re.search(r'(?:file|document|search for|find|named|called|get|fetch)\s+(?:the\s+)?([A-Za-z0-9_\-\.]+)', text, re.IGNORECASE)
            if file_match:
                name_cand = file_match.group(1).strip()
                if name_cand.casefold() not in ("the", "a", "an", "in", "to", "for", "db", "database", "all", "our", "any", "from", "data", "base", "file", "files"):
                    return ("SELECT id, folder, filename, relative_path, file_type, size_bytes FROM public.files WHERE filename LIKE %s OR summary LIKE %s LIMIT 25", (f"%{name_cand}%", f"%{name_cand}%"))

            # 2c. Substantial keywords
            noise_words = {"get", "find", "search", "show", "list", "the", "a", "an", "for", "from", "in", "to", "of", "all", "my", "our", "me", "file", "files", "document", "documents", "database", "data", "base", "db", "this", "that", "please", "can", "you", "i", "need", "want", "check", "look", "up"}
            query_words = [w for w in re.findall(r'\w+', lower) if w not in noise_words and len(w) > 2]
            if query_words:
                search_term = query_words[0]
                return ("SELECT id, folder, filename, relative_path, file_type, size_bytes FROM public.files WHERE filename LIKE %s OR summary LIKE %s LIMIT 25", (f"%{search_term}%", f"%{search_term}%"))

            return ("SELECT id, folder, filename, relative_path, file_type, size_bytes FROM public.files LIMIT 25", ())

        # 3. Ledger balances, transactions, and payment records
        if any(w in lower for w in ("transaction", "transactions", "ledger", "balance", "balances", "debit", "credit", "merchant", "expense", "expenses", "payment", "payments")):
            if any(w in lower for w in ("debit", "credit")):
                tx_type = "Debit" if "debit" in lower else "Credit"
                return ("SELECT transaction_id, date, account_id, transaction_type, category, merchant, amount, currency, status FROM public.transactions WHERE transaction_type = %s LIMIT 25", (tx_type,))
            if "pending" in lower:
                return ("SELECT transaction_id, date, account_id, transaction_type, category, merchant, amount, currency, status FROM public.transactions WHERE status = 'Pending' LIMIT 25", ())
            if "completed" in lower:
                return ("SELECT transaction_id, date, account_id, transaction_type, category, merchant, amount, currency, status FROM public.transactions WHERE status = 'Completed' LIMIT 25", ())
            return ("SELECT transaction_id, date, account_id, transaction_type, category, merchant, amount, currency, status FROM public.transactions LIMIT 25", ())

        # 4. Invoice queries
        if any(w in lower for w in ("invoice", "invoices", "overdue", "billing", "unpaid")):
            for cust in ("Acme", "Apex", "Globex", "Initech", "Hooli", "Nexa", "Vertex", "Metro", "CloudNova"):
                if cust.casefold() in lower:
                    return ("SELECT id, customer, amount, status, due_date FROM public.invoices WHERE customer LIKE %s LIMIT 25", (f"%{cust}%",))
            if "overdue" in lower:
                return ("SELECT id, customer, amount, status, due_date FROM public.invoices WHERE status = 'Overdue' LIMIT 25", ())
            if "pending" in lower:
                return ("SELECT id, customer, amount, status, due_date FROM public.invoices WHERE status = 'Pending' LIMIT 25", ())
            if "paid" in lower:
                return ("SELECT id, customer, amount, status, due_date FROM public.invoices WHERE status = 'Paid' LIMIT 25", ())
            return ("SELECT id, customer, amount, status, due_date FROM public.invoices LIMIT 25", ())

        # 5. Contract queries
        if any(w in lower for w in ("contract", "contracts", "renewal", "renewals", "agreement", "msa")):
            for cust in ("Acme", "Apex", "Globex", "Initech", "Hooli", "Nexa", "Vertex", "Metro", "CloudNova"):
                if cust.casefold() in lower:
                    return ("SELECT id, customer, contract_type, annual_value, renewal_date FROM public.contracts WHERE customer LIKE %s LIMIT 25", (f"%{cust}%",))
            if "renewal" in lower:
                return ("SELECT id, customer, contract_type, annual_value, renewal_date FROM public.contracts ORDER BY renewal_date ASC LIMIT 25", ())
            return ("SELECT id, customer, contract_type, annual_value, renewal_date FROM public.contracts LIMIT 25", ())

        # 6. Customer & client queries
        if any(w in lower for w in ("customer", "customers", "client", "clients", "segment", "credit score")):
            for cust in ("Acme", "Apex", "Globex", "Initech", "Hooli", "Nexa", "Vertex", "Metro", "CloudNova"):
                if cust.casefold() in lower:
                    return ("SELECT id, name, city, customer_type, industry, annual_value, status FROM public.customers WHERE name LIKE %s LIMIT 25", (f"%{cust}%",))
            for city in ("Pune", "Hyderabad", "Mumbai", "Bengaluru", "Chennai", "Delhi"):
                if city.casefold() in lower:
                    return ("SELECT id, name, city, customer_type, industry, annual_value, status FROM public.customers WHERE city = %s LIMIT 25", (city,))
            return ("SELECT id, name, city, customer_type, industry, annual_value, status FROM public.customers LIMIT 25", ())

        # 7. Project & task queries
        if any(w in lower for w in ("task", "tasks", "to-do", "todo")):
            return ("SELECT id, task_id, project_id, task, owner, status, priority, due_date FROM public.tasks LIMIT 25", ())
        if any(w in lower for w in ("project", "projects", "milestone", "milestones")):
            return ("SELECT id, project_id, name, owner, budget, status, priority FROM public.projects LIMIT 25", ())

        # 8. Department / budget queries
        if any(w in lower for w in ("department", "departments", "dept", "budget")):
            return ("SELECT id, name, budget, manager FROM public.departments LIMIT 25", ())

        # 9. Employee / team / people / candidate queries
        if any(w in lower for w in ("employee", "employees", "staff", "team", "engineer", "salary", "who works", "worker", "candidate", "applicant", "person", "called", "named")):
            for name in ("Harish", "Priya", "David", "Rahul", "Kavita", "Deepak", "Sarah", "Alex"):
                if name.casefold() in lower:
                    return ("SELECT id, name, department, role, salary FROM public.employees WHERE name LIKE %s LIMIT 10", (f"%{name}%",))
            name_match = re.search(r'(?:called|named|employee|person|candidate|check)\s+([A-Za-z]+)', text, re.IGNORECASE)
            if name_match:
                name_val = name_match.group(1).strip()
                if name_val.casefold() not in ("called", "named", "for", "the", "a", "an", "is", "in", "to", "at", "any", "all", "our", "my", "me"):
                    return ("SELECT id, name, department, role, salary FROM public.employees WHERE name LIKE %s LIMIT 10", (f"%{name_val}%",))
            for dept in ("Engineering", "Finance", "HR", "Sales", "Operations", "Executive"):
                if dept.casefold() in lower:
                    return ("SELECT id, name, department, role, salary FROM public.employees WHERE department = %s LIMIT 25", (dept,))
            return ("SELECT id, name, department, role, salary FROM public.employees LIMIT 25", ())

        # 10. Database table inspection / catalog queries
        if any(w in lower for w in ("table", "tables", "schema", "record", "records")):
            return ("SELECT id, folder, filename, relative_path, file_type, size_bytes FROM public.files LIMIT 25", ())

        # General default
        return ("SELECT id, name, department, role FROM public.employees LIMIT 15", ())
