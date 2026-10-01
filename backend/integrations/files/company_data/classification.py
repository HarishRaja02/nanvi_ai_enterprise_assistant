"""Department classification and RBAC folder policy mapping for company documents."""
from __future__ import annotations

from backend.security.authorization.rbac import Role

STOPWORDS = frozenset({
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or", "is",
    "are", "was", "were", "what", "which", "who", "whom", "this", "that", "these",
    "those", "am", "been", "being", "have", "has", "had", "do", "does", "did",
    "can", "could", "should", "would", "may", "might", "must", "shall", "will",
    "our", "my", "your", "their", "its", "from", "by", "with", "about", "into",
    "tell", "me", "show", "give", "find", "get", "please", "nanvi", "company",
    "data", "information", "details", "all", "available", "related",
    "hi", "hello", "hey", "thanks", "thank", "welcome", "section", "folder",
    "file", "files", "document", "documents",
})

# Folder RBAC permissions map
FOLDER_ROLES = {
    "Customers": {Role.SUPERIOR, Role.SUPERVISOR, Role.CEO, Role.FINANCE, Role.HR, Role.MANAGER, Role.IT_ADMIN},
    "Finance": {Role.SUPERIOR, Role.SUPERVISOR, Role.CEO, Role.FINANCE, Role.MANAGER, Role.IT_ADMIN},
    "HR": {Role.SUPERIOR, Role.SUPERVISOR, Role.PROJECT_ENGINEER, Role.EMPLOYEE, Role.CEO, Role.HR, Role.MANAGER, Role.IT_ADMIN},
    "Projects": {Role.SUPERIOR, Role.SUPERVISOR, Role.PROJECT_ENGINEER, Role.CEO, Role.FINANCE, Role.HR, Role.MANAGER, Role.EMPLOYEE, Role.IT_ADMIN},
    "Contracts": {Role.SUPERIOR, Role.SUPERVISOR, Role.CEO, Role.FINANCE, Role.MANAGER, Role.IT_ADMIN},
    "Resumes": {Role.SUPERIOR, Role.SUPERVISOR, Role.CEO, Role.FINANCE, Role.HR, Role.MANAGER, Role.IT_ADMIN},
    "Uploads": {Role.SUPERIOR, Role.SUPERVISOR, Role.PROJECT_ENGINEER, Role.EMPLOYEE, Role.CEO, Role.FINANCE, Role.HR, Role.MANAGER, Role.IT_ADMIN},
    "General": {Role.SUPERIOR, Role.SUPERVISOR, Role.PROJECT_ENGINEER, Role.EMPLOYEE, Role.CEO, Role.FINANCE, Role.HR, Role.MANAGER, Role.IT_ADMIN},
}


def _classify_department(parts: tuple[str, ...], filename: str, base_root_name: str) -> tuple[str, str]:
    """Determine (department, subfolder) for any file in any directory structure."""
    path_str = "/".join(parts).casefold()
    fn_lower = filename.casefold()
    combined = f"{path_str}/{fn_lower}"

    if not parts:
        return "General", ""

    # Check for department keywords in path or filename
    if any(k in combined for k in ("finance", "invoice", "invoices", "billing", "payable", "receivable", "accounting", "tax", "budget", "expense", "expenses")):
        dept = "Finance"
    elif any(k in combined for k in ("hr", "resumes", "resume", "employees", "employee", "payroll", "headcount", "benefits", "hiring", "recruitment", "handbook")):
        dept = "HR"
    elif any(k in combined for k in ("contract", "contracts", "agreement", "agreements", "nda", "msa", "sla", "renewals", "renewal", "legal")):
        dept = "Contracts"
    elif any(k in combined for k in ("project", "projects", "sprint", "engineering", "tech", "phoenix", "deliverable", "architecture", "audit", "validation")):
        dept = "Projects"
    elif any(k in combined for k in ("customer", "customers", "client", "clients", "sales", "crm", "acme")):
        dept = "Customers"
    elif any(k in combined for k in ("upload", "uploads")):
        dept = "Uploads"
    else:
        # Check if first folder matches standard dept name case-insensitively
        direct_name = parts[0]
        known_map = {d.casefold(): d for d in FOLDER_ROLES.keys()}
        dept = known_map.get(direct_name.casefold(), direct_name)

    subfolder = "/".join(parts[1:]) if len(parts) > 1 else ("/".join(parts) if parts and parts[0] != dept else "")
    return dept, subfolder
