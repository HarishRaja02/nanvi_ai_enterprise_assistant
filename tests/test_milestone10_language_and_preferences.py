"""Milestone 10 Unit & Integration Tests: Indian Languages, Vocabulary Biasing, Adaptive Verbosity, and Preferences.

Tests Section 7.6, Section 7.7, and Section 8 of docs/NANVI_SPEC.md.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.chat.context_engine import (
    context_manager,
    detect_code_switching,
    detect_verbosity_command,
    UserPreferences,
)
from backend.chat.response_planner import (
    human_response_planner,
    SpokenNumberFormatter,
)
from backend.chat.vocabulary_biasing import (
    apply_phonetic_corrections,
    get_vocabulary_summary,
    WHISPER_BIASING_PROMPT,
)
from backend.security.authorization import Role, UserAttributes


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers(client: TestClient):
    resp = client.post(
        "/api/dev/token",
        json={"role": "CEO", "department": "Executive"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestLanguageAndCodeSwitching:
    """Test code-switching detection and Indian language markers."""

    def test_detect_hinglish_markers(self):
        assert detect_code_switching("Asteron Technologies ka invoice dikhao") == "hinglish"
        assert detect_code_switching("Q3 ka revenue kitna hai?") == "hinglish"
        assert detect_code_switching("theek hai, email bhejo") == "hinglish"
        assert detect_code_switching("Project Phoenix ka budget batao") == "hinglish"

    def test_detect_tamil_markers(self):
        assert detect_code_switching("Revenue last quarter evvalavu?") == "ta-IN"
        assert detect_code_switching("eppadi irukku status?") == "ta-IN"

    def test_detect_standard_english(self):
        assert detect_code_switching("What is the revenue for Q3?") == "en-IN"
        assert detect_code_switching("Show me the biggest customers") == "en-IN"
        assert detect_code_switching("") == "en-IN"


class TestAdaptiveVerbosityCommands:
    """Test explicit voice command detection for adjusting verbosity."""

    def test_concise_commands(self):
        assert detect_verbosity_command("be more brief") == "concise"
        assert detect_verbosity_command("keep it concise") == "concise"
        assert detect_verbosity_command("shorter please") == "concise"
        assert detect_verbosity_command("make it short") == "concise"
        assert detect_verbosity_command("concise mode") == "concise"
        assert detect_verbosity_command("too long") == "concise"

    def test_detailed_commands(self):
        assert detect_verbosity_command("tell me more") == "detailed"
        assert detect_verbosity_command("give me more detail") == "detailed"
        assert detect_verbosity_command("explain further") == "detailed"
        assert detect_verbosity_command("be more detailed") == "detailed"
        assert detect_verbosity_command("detailed mode") == "detailed"
        assert detect_verbosity_command("elaborate") == "detailed"

    def test_normal_commands(self):
        assert detect_verbosity_command("normal mode") == "normal"
        assert detect_verbosity_command("balanced mode") == "normal"
        assert detect_verbosity_command("reset verbosity") == "normal"
        assert detect_verbosity_command("standard verbosity") == "normal"

    def test_non_verbosity_queries(self):
        assert detect_verbosity_command("What was the net profit for last month?") is None
        assert detect_verbosity_command("Show the list of open invoices") is None


class TestSpokenNumberFormatting:
    """Test spoken number formatting with Indian numbering and currencies."""

    def test_inr_abbreviations(self):
        assert "18.4 crore rupees" in SpokenNumberFormatter.format("Total sales reached ₹18.4 Cr.")
        assert "12 lakh rupees" in SpokenNumberFormatter.format("Contract value is ₹12L.")
        assert "40 lakh rupees" in SpokenNumberFormatter.format("The budget is Rs 40 Lakhs.")
        assert "15 lakh rupees" in SpokenNumberFormatter.format("Spend was ₹15 Lacs.")

    def test_inr_comma_digits(self):
        # 18,40,00,000 is 18.4 crore
        formatted = SpokenNumberFormatter.format("Revenue was ₹18,40,00,000 for the period.")
        assert "18.4 crore rupees" in formatted

    def test_plan_response_adapts_verbosity(self):
        answer = "Quarterly revenue was 18.4 crore rupees. Enterprise sales grew by 14 percent. Top driver was CloudNova. Renewal rate is 98 percent."
        
        # Concise should yield 1 sentence
        plan_concise = human_response_planner.plan_response(
            answer=answer,
            query="revenue",
            verbosity_preference="concise",
        )
        assert "Quarterly revenue" in plan_concise.spoken_response
        assert "Enterprise sales" not in plan_concise.spoken_response
        
        # Detailed should yield up to 4 sentences
        plan_detailed = human_response_planner.plan_response(
            answer=answer,
            query="revenue",
            verbosity_preference="detailed",
        )
        assert "Enterprise sales" in plan_detailed.spoken_response
        assert "CloudNova" in plan_detailed.spoken_response


class TestEnterpriseVocabularyBiasing:
    """Test enterprise vocabulary biasing and phonetic correction."""

    def test_vocabulary_prompt_contents(self):
        assert "Asteron Technologies" in WHISPER_BIASING_PROMPT
        assert "CloudNova" in WHISPER_BIASING_PROMPT
        assert "Project Phoenix" in WHISPER_BIASING_PROMPT
        assert "EBITDA" in WHISPER_BIASING_PROMPT
        assert "Lakh" in WHISPER_BIASING_PROMPT
        assert "Crore" in WHISPER_BIASING_PROMPT

    def test_phonetic_corrections(self):
        assert apply_phonetic_corrections("Show aster on tech invoices") == "Show Asteron Technologies invoices"
        assert apply_phonetic_corrections("Status of cloud nova contract") == "Status of CloudNova contract"
        assert apply_phonetic_corrections("Update on project fenix") == "Update on Project Phoenix"
        assert apply_phonetic_corrections("What is our ebidta margin?") == "What is our EBITDA margin?"
        assert apply_phonetic_corrections("Budget is 25 lacs") == "Budget is 25 lakh"


class TestVoicePreferenceEndpoints:
    """Test /voice/preferences and /voice/vocabulary endpoints and command handling."""

    def test_get_vocabulary(self, client: TestClient, auth_headers: dict[str, str]):
        resp = client.get("/api/voice/vocabulary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "companies" in data
        assert "Asteron Technologies" in data["companies"]
        assert "projects" in data
        assert "Project Phoenix" in data["projects"]

    def test_get_and_update_preferences(self, client: TestClient, auth_headers: dict[str, str]):
        conv_id = "test_pref_conv_1"
        # Get defaults
        resp = client.get(f"/api/voice/preferences?conversation_id={conv_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert "preferences" in resp.json()

        # Update preferences
        resp = client.post(
            "/api/voice/preferences",
            headers=auth_headers,
            json={"conversation_id": conv_id, "verbosity": "detailed", "language": "hinglish"},
        )
        assert resp.status_code == 200

    def test_verbal_verbosity_command_interception(self, client: TestClient, auth_headers: dict[str, str]):
        resp = client.post(
            "/api/voice/respond",
            headers=auth_headers,
            json={"query": "be more brief", "conversation_id": "test_verbal_pref_conv"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["capability"] == "preferences"
        assert "concise" in data["spoken_text"].lower()
        assert data["user_preferences"]["verbosity"] == "concise"
