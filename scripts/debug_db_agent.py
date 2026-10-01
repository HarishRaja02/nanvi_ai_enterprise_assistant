import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.bootstrap import create_chat_service
from backend.agents.models import AgentRequest, Capability
from backend.security.authorization import UserAttributes, Role
import traceback

service = create_chat_service()
user = UserAttributes('u1', 'enterprise-tenant', 'Finance', frozenset({Role.FINANCE, Role.CEO}))
req = AgentRequest(request_id='r1', user=user, query='Query production database for ledger balances, SQL tables, and transaction records')
db_agent = service._orchestrator.agents[Capability.DATABASE]

try:
    sql, params = db_agent._planner.plan(req.query, req.user)
    print("PLANNED SQL:", sql)
    print("PLANNED PARAMS:", params)
    res = db_agent._tool.read(req.user, sql, params)
    print("TOOL RESULT COLUMNS:", res.columns)
    print("TOOL RESULT ROWS COUNT:", len(res.rows))
except Exception as e:
    traceback.print_exc()
