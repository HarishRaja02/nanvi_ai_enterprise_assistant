from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.voice_routes import clean_spoken_text, extract_important_points
from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers(client: TestClient):
    resp = client.post(
        "/api/dev/token",
        json={"role": "Finance", "department": "Finance"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_clean_spoken_text_strips_markdown_and_tables():
    raw = """
### Quarterly Financial Summary
According to the report [Source 1], revenue increased by 12%.

| Metric | Value |
| --- | --- |
| Revenue | $4.2M |
| Expenses | $1.1M |

* Software expenses grew 8%.
* Vendor contracts renewed.

Check https://internal.company.com/reports for details.
```sql
SELECT * FROM ledger;
```
"""
    spoken = clean_spoken_text(raw)
    assert "###" not in spoken
    assert "[Source 1]" not in spoken
    assert "https://" not in spoken
    assert "```" not in spoken
    assert "revenue increased by 12%" in spoken.lower()
    assert "software expenses grew 8%" in spoken.lower()


def test_extract_important_points_finds_key_facts():
    answer = """
Here are the key findings from your files:
* Revenue reached 4.2 million dollars in Q2.
* Cloud infrastructure cost grew by 8 percent.
* Three vendor contracts were renewed through 2027.
"""
    points = extract_important_points(answer, [])
    assert len(points) == 3
    assert any("4.2 million" in p for p in points)
    assert any("infrastructure" in p for p in points)


def test_voice_respond_endpoint_with_auth(client: TestClient, auth_headers: dict[str, str]):
    response = client.post(
        "/api/voice/respond",
        json={"query": "Hello Nanvi", "rag_enabled": True},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "conversation_id" in data
    assert "answer" in data
    assert "spoken_text" in data
    assert "important_points" in data
    assert isinstance(data["important_points"], list)
    assert "sources" in data
    assert "history" in data


def test_clean_spoken_text_abbreviations_and_humanization():
    raw = "The avg. profit grew in Q3 vs. Q2, e.g., cloud revenue hit $5M, etc."
    spoken = clean_spoken_text(raw)
    assert "for example" in spoken
    assert "versus" in spoken
    assert "Quarter 3" in spoken
    assert "5 million dollars" in spoken
    assert "and so forth" in spoken
    assert "*" not in spoken


def test_voice_synthesize_endpoint(client: TestClient, auth_headers: dict[str, str]):
    response = client.post(
        "/api/voice/synthesize",
        json={"text": "Hello, I am Nanvi. How can I help you today?", "profile_id": "nanvi-warm"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert len(response.content) > 1000


def test_voice_synthesize_empty_text_rejected(client: TestClient, auth_headers: dict[str, str]):
    response = client.post(
        "/api/voice/synthesize",
        json={"text": "   ", "profile_id": "nanvi-warm"},
        headers=auth_headers,
    )
    assert response.status_code in {400, 422}

