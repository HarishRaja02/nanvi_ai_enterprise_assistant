import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.bootstrap import create_chat_service
from backend.agents.models import AgentRequest, Capability
from backend.security.authorization import UserAttributes, Role

service = create_chat_service()
user = UserAttributes(
    user_id="test-user",
    tenant_id="enterprise-tenant",
    department="Finance",
    roles=frozenset({Role.FINANCE, Role.CEO}),
)

query = "Query production database for ledger balances, SQL tables, and transaction records"
agent_req = AgentRequest(request_id="r1", user=user, query=query)
state = service._orchestrator.invoke(agent_req, forced_capability=Capability.DATABASE)
print("ORCHESTRATOR RESPONSE:", state.response)

context = service._prompt_context.build(
    query,
    tuple([state.response])
)

rendered = service._prompt_context.render(context)
print("\n=== RENDERED PROMPT ===")
print(rendered[:1000] + " ... [TRUNCATED] ... " + rendered[-500:])

print("\n=== CALLING LLM ===")
try:
    resp = service._answerer._provider.generate(rendered, system=context.system_policy)
    print("\n=== RAW LLM RESPONSE ===")
    print(resp)
except Exception as e:
    import traceback
    traceback.print_exc()
