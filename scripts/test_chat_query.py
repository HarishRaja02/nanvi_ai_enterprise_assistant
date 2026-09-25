import sys
import io
# Ensure stdout uses utf-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.bootstrap import create_chat_service
from backend.chat.models import ChatRequest
from backend.security.authorization import UserAttributes, Role

def test_query():
    service = create_chat_service()
    user = UserAttributes(
        user_id="test-user",
        tenant_id="enterprise-tenant",
        department="Finance",
        roles=frozenset({Role.FINANCE, Role.CEO, Role.MANAGER}),
    )

    queries = [
        "Query production database for ledger balances, SQL tables, and transaction records",
        "search for the file transactions_01.csv in db",
        "show me files in Finance folder in db",
    ]

    for q in queries:
        print(f"\n==========================================")
        print(f"QUERY: {q}")
        req = ChatRequest(query=q, conversation_id="test-convo")
        response = service.ask(user=user, request=req)
        print(f"ANSWER:\n{response.answer}")
        print(f"CAPABILITY: {response.capability}")
        print(f"SOURCES: {len(response.sources)}")
        for s in response.sources:
            print(f"  - [{s.source_type}] {s.display_name} ({s.reference_id})")

if __name__ == "__main__":
    test_query()
