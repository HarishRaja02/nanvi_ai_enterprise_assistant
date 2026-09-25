import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.integrations.files.company_data_service import CompanyDataService
from backend.security.authorization import UserAttributes

from backend.security.authorization.rbac import Role

svc = CompanyDataService.get_instance()
user = UserAttributes("test-user", "enterprise-tenant", "Engineering", (Role.CEO,))

print("Total indexed files:", len(svc.files))
print("Total chunks:", len(svc.chunks))

q = "what is the leave policy in employee_handbook_2026.pdf?"
res = svc.search_files(user, q)
print("\n=== search_files answer ===")
print(res.answer_content[:400].encode("ascii", "replace").decode("ascii"))
print("requires_llm:", getattr(res, "requires_llm", False))

res2 = svc.search(user, q)
print("\n=== search answer ===")
print(res2.answer_content[:400].encode("ascii", "replace").decode("ascii"))
