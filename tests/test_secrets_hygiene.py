"""Tests for secrets hygiene:
- No hardcoded Tavily key in services/web_search.py
- search_web degrades gracefully when TAVILY_API_KEY is unset
- run_web_agent returns explicit error when TAVILY_API_KEY is unset
- Credential files are listed in .gitignore
- .env.example exists with placeholder values
"""
from pathlib import Path
import pytest

from backend.integrations.web import search_web
from backend.agents.capability_agents import run_web_agent


def test_no_hardcoded_tavily_key_in_source():
    """backend/integrations/web/service.py must not contain any hardcoded tvly- keys."""
    web_search_file = Path("backend/integrations/web/service.py")
    content = web_search_file.read_text(encoding="utf-8")
    assert "tvly-dev" not in content
    assert "tvly-" not in content


def test_tavily_search_degrades_gracefully_when_key_absent(monkeypatch: pytest.MonkeyPatch):
    """search_web must return empty list without crashing when TAVILY_API_KEY is not in env."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    results = search_web("test query")
    assert results == []


def test_run_web_agent_returns_clear_error_when_key_absent(monkeypatch: pytest.MonkeyPatch):
    """run_web_agent must return an explicit message stating TAVILY_API_KEY is not configured."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    answer = run_web_agent("test question")
    assert "TAVILY_API_KEY is not configured" in answer


def test_gitignore_contains_credential_files():
    """Verify .gitignore includes sensitive files."""
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
    assert "backend/storage/user_email_accounts.json" in gitignore
    assert ".vercel/.env.preview.local" in gitignore


def test_env_example_contains_placeholders():
    """.env.example must exist and must contain safe placeholder values only."""
    example_path = Path(".env.example")
    assert example_path.exists()
    content = example_path.read_text(encoding="utf-8")
    assert "placeholder" in content
    assert "tvly-dev" not in content
