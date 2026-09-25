from __future__ import annotations

import sys
sys.stdout.reconfigure(encoding='utf-8')

from backend.bootstrap import create_chat_service
from backend.chat.models import ChatRequest
from backend.security.authorization import UserAttributes, Role


def main():
    svc = create_chat_service()
    user = UserAttributes("u-ceo", "enterprise-tenant", "Executive", frozenset({Role.CEO}))

    print("\n=================== 1. DATA ANALYSIS ===================")
    r1 = svc.ask(user, ChatRequest("What is the average salary of employees?"))
    print("CAPABILITY:", r1.capability)
    print("ANSWER:\n", r1.answer)

    print("\n=================== 2. DATABASE QUERY ===================")
    r2 = svc.ask(user, ChatRequest("Show overdue invoices"))
    print("CAPABILITY:", r2.capability)
    print("ANSWER:\n", r2.answer)

    print("\n=================== 3. REPORT GENERATION ===================")
    r3 = svc.ask(user, ChatRequest("Generate an executive report in Excel"))
    print("CAPABILITY:", r3.capability)
    print("ANSWER:\n", r3.answer)
    print("REPORT ID:", r3.report_id)

    print("\n=================== 4. KNOWLEDGE RETRIEVAL ===================")
    r4 = svc.ask(user, ChatRequest("What are the customer SLAs?"))
    print("CAPABILITY:", r4.capability)
    print("ANSWER:\n", r4.answer)
    print("SOURCES COUNT:", len(r4.sources))


if __name__ == "__main__":
    main()
