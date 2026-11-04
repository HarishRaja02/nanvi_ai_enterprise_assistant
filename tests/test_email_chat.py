from fastapi.testclient import TestClient
from backend.main import app

def test_chat_searches_gmail_and_files():
    client = TestClient(app)
    t_resp = client.post(
        "/api/dev/token",
        json={"role": "CEO", "department": "Executive"},
    )
    assert t_resp.status_code == 200
    token = t_resp.json()["access_token"]

    chat_resp = client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "What is the status of Project Phoenix and what did Rahul send in email?"},
    )
    assert chat_resp.status_code == 200
    data = chat_resp.json()
    print("\nCAPABILITY:", data.get("capability"))
    print("\nANSWER:\n", data.get("answer"))
    print("\nSOURCES:\n", data.get("sources"))
    assert "Sprint 24" in data["answer"] or "Rahul Patel" in data["answer"] or "Phoenix" in data["answer"]
    assert any(s.get("source_type") == "email" or "email" in str(s) for s in data["sources"])
