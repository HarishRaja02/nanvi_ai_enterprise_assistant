import httpx

def test_chat_searches_gmail_and_files():
    t_resp = httpx.post(
        "http://127.0.0.1:8000/api/dev/token",
        json={"role": "CEO", "department": "Executive"},
        timeout=10.0,
    )
    assert t_resp.status_code == 200
    token = t_resp.json()["access_token"]

    chat_resp = httpx.post(
        "http://127.0.0.1:8000/api/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "What is the status of Project Phoenix and what did Rahul send in email?"},
        timeout=60.0,
    )
    assert chat_resp.status_code == 200
    data = chat_resp.json()
    print("\nCAPABILITY:", data.get("capability"))
    print("\nANSWER:\n", data.get("answer"))
    print("\nSOURCES:\n", data.get("sources"))
    assert "Sprint 24" in data["answer"] or "Rahul Patel" in data["answer"] or "Phoenix" in data["answer"]
    assert any(s.get("source_type") == "email" or "email" in str(s) for s in data["sources"])
