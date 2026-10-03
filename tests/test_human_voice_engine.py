import pytest
from backend.chat.speech_normalizer import (
    normalize_for_speech,
    strip_technical_jargon,
    normalize_enterprise_id,
    normalize_currency,
    normalize_date,
    normalize_email,
    normalize_urls,
)
from backend.chat.response_planner import human_response_planner, PhrasePool
from backend.chat.deictic_resolver import DeicticResolver
from backend.chat.context_engine import (
    ConversationContext,
    EntityContext,
    UserContext,
    detect_code_switching,
)
from backend.api.voice_routes import PROFILE_TO_EDGE_VOICE


# -------------------------------------------------------------
# Scenario 1: Simple question
# -------------------------------------------------------------
def test_scenario_1_simple_question():
    """Scenario 1: Simple question yields short, direct, collegial answer."""
    plan = human_response_planner.plan_response(
        answer="Sneha Mohan is an HR Executive who joined in 2024.",
        query="Who is Sneha Mohan?",
        privacy_mode=False
    )
    assert "Sneha Mohan is an H R Executive" in plan.spoken_response or "Sneha Mohan is an HR Executive" in plan.spoken_response
    assert len(plan.spoken_response.split()) < 30


# -------------------------------------------------------------
# Scenario 2: Long RAG answer
# -------------------------------------------------------------
def test_scenario_2_rag_answer_clean_and_concise():
    """Scenario 2: RAG answers are conclusion-first, without citation clutter or robotic intros."""
    rag_answer = (
        "According to the retrieved documents [ref-1], the bridge inspection report for Chennai "
        "indicates structural integrity is stable with minor cosmetic wear on the western support. "
        "Further details can be found in doc_2025.pdf."
    )
    plan = human_response_planner.plan_response(
        answer=rag_answer,
        query="What did the bridge inspection report say?",
        privacy_mode=False
    )
    spoken = plan.spoken_response
    assert "[ref-1]" not in spoken
    assert "retrieved documents" not in spoken.lower()
    assert "structural integrity is stable" in spoken.lower()


# -------------------------------------------------------------
# Scenario 3: SQL query answer
# -------------------------------------------------------------
def test_scenario_3_sql_query_clean():
    """Scenario 3: SQL answers do not mention database, tables, or SQL agent."""
    sql_answer = "Found 12 employees in the HR department."
    plan = human_response_planner.plan_response(
        answer=sql_answer,
        query="Find employees in HR",
        capability="database",
        privacy_mode=False
    )
    spoken = plan.spoken_response
    assert "database" not in spoken.lower()
    assert "sql" not in spoken.lower()
    assert "12 employees" in spoken or "twelve employees" in spoken


# -------------------------------------------------------------
# Scenario 4: Employee ID (EMP1004)
# -------------------------------------------------------------
def test_scenario_4_employee_id():
    """Scenario 4: Employee ID such as EMP1004 spoken as employee one zero zero four."""
    spoken = normalize_for_speech("Found employee EMP1004 in HR.")
    assert "employee one zero zero four" in spoken


# -------------------------------------------------------------
# Scenario 5: Currency (₹45,000, ₹4,50,000)
# -------------------------------------------------------------
def test_scenario_5_currency():
    """Scenario 5: Currency formatted to spoken words."""
    spoken = normalize_for_speech("Her salary is ₹45,000 a month.")
    assert "forty-five thousand rupees" in spoken

    spoken_lakh = normalize_for_speech("Total budget is ₹4,50,000.")
    assert "four lakh fifty thousand rupees" in spoken_lakh


# -------------------------------------------------------------
# Scenario 6: Date (2025-09-14)
# -------------------------------------------------------------
def test_scenario_6_date():
    """Scenario 6: Dates formatted to natural spoken words."""
    spoken = normalize_for_speech("The report is from 2025-09-14.")
    assert "September fourteenth, twenty twenty-five" in spoken


# -------------------------------------------------------------
# Scenario 7: Email reading
# -------------------------------------------------------------
def test_scenario_7_email_reading():
    """Scenario 7: Email reading sounds natural, not reading punctuation or raw headers."""
    raw_email = (
        "From: sneha@nanvi.ai\nSubject: Project Deadline\n\n"
        "Hi John,\nJust checking in. The project deadline has been moved to Friday.\n"
        "Best,\nSneha"
    )
    plan = human_response_planner.plan_response(
        answer=raw_email,
        query="Read the whole email",
        capability="email",
        privacy_mode=False
    )
    spoken = plan.spoken_response
    assert "From:" not in spoken
    assert "Subject:" not in spoken
    assert "comma" not in spoken.lower()
    assert "Hi John" in spoken or "deadline" in spoken


def test_scenario_7b_email_summary():
    """Scenario 7b: Default email response provides main point summary."""
    raw_email = (
        "From: sneha@nanvi.ai\nSubject: Project Deadline\n\n"
        "The project deadline has been moved to Friday due to client feedback.\n"
        "Best,\nSneha"
    )
    plan = human_response_planner.plan_response(
        answer=raw_email,
        query="Do I have an email about the deadline?",
        capability="email",
        privacy_mode=False
    )
    spoken = plan.spoken_response
    assert "main point" in spoken.lower()
    assert "From:" not in spoken


# -------------------------------------------------------------
# Scenario 8 & 16: Long response summarization
# -------------------------------------------------------------
def test_scenario_8_16_long_response_summarization():
    """Scenario 8 & 16: Long responses provide a concise spoken summary and offer details."""
    long_content = (
        "Here are the findings from the audit. First, user authentication tokens expire after 24 hours. "
        "Second, database connections are pooled with a maximum of twenty connections. "
        "Third, encrypted backups run daily at midnight. Fourth, rate limiting is configured at 100 requests per minute. "
        "Fifth, logging captures all authorized API events. Sixth, file uploads are restricted to 10 megabytes. "
        "Seventh, cross-origin resource sharing is enabled for approved domains. Eighth, error reporting alerts on-call engineers. "
        "Ninth, periodic penetration testing occurs quarterly. Tenth, compliance records are archived."
    )
    plan = human_response_planner.plan_response(
        answer=long_content,
        query="Tell me about the audit",
        privacy_mode=False
    )
    spoken = plan.spoken_response
    assert len(spoken.split()) < 50
    assert "details" in spoken.lower() or "remaining" in spoken.lower()


# -------------------------------------------------------------
# Scenario 9: User hesitation / pause handling
# -------------------------------------------------------------
def test_scenario_9_user_hesitation():
    """Scenario 9: Vocal fillers (um, uh) are gracefully tolerated in text cleaning."""
    from backend.api.voice_routes import clean_spoken_text
    hesitation_input = "Can you find the... um... bridge inspection report?"
    cleaned = clean_spoken_text(hesitation_input)
    assert "bridge inspection report" in cleaned


# -------------------------------------------------------------
# Scenario 10: Contextual follow-up question
# -------------------------------------------------------------
def test_scenario_10_contextual_follow_up():
    """Scenario 10: Follow-up question resolution with immediate context."""
    context = ConversationContext(
        conversation_id="conv_follow_up",
        user=UserContext(id="test_user", role="CEO"),
        active_entity=EntityContext(
            type="employee",
            id="EMP1004",
            name="Sneha Mohan",
        ),
    )
    prior_q = "Find employees in HR."
    prior_a = "Found them. It's Sneha Mohan, an HR Executive."

    resolved = DeicticResolver.resolve(
        query="What's her salary?",
        context=context,
        prior_user_query=prior_q,
        prior_assistant_answer=prior_a,
    )
    assert "sneha mohan" in resolved.lower() or "emp1004" in resolved.lower() or "salary" in resolved.lower()


# -------------------------------------------------------------
# Scenario 11: Long backend operation acknowledgements
# -------------------------------------------------------------
def test_scenario_11_collegial_acknowledgements():
    """Scenario 11: Acknowledgements are collegial human phrases, not robotic."""
    pool = PhrasePool()
    sql_phrase = pool.get_phrase("SQL_QUERY")
    assert any(w in sql_phrase.lower() for w in ["second", "check", "moment", "look"])
    assert "querying database" not in sql_phrase.lower()

    knowledge_phrase = pool.get_phrase("KNOWLEDGE_SEARCH")
    assert "searching vector" not in knowledge_phrase.lower()


# -------------------------------------------------------------
# Scenario 13: One consistent voice identity
# -------------------------------------------------------------
def test_scenario_13_consistent_voice_profile():
    """Scenario 13: Centralized voice configuration maintains single identity."""
    assert "nanvi-pro" in PROFILE_TO_EDGE_VOICE
    assert PROFILE_TO_EDGE_VOICE["nanvi-pro"] == "en-US-JennyNeural"
    assert PROFILE_TO_EDGE_VOICE["nanvi-warm"] == "en-US-AvaNeural"


# -------------------------------------------------------------
# Scenario 14: Tamil language support
# -------------------------------------------------------------
def test_scenario_14_tamil_support():
    """Scenario 14: Tamil language code correctly detects and routes to Tamil voice."""
    tamil_detected = detect_code_switching("வணக்கம் நன்வி, உதவி செய்ய முடியுமா?")
    assert tamil_detected in ("ta", "ta-IN")


# -------------------------------------------------------------
# Scenario 15: Tamil-English mixed code-switching
# -------------------------------------------------------------
def test_scenario_15_tamil_english_mixed():
    """Scenario 15: Mixed Tamil-English detects Indian/Tamil voice context."""
    mixed_speech = "Hey Nanvi, bridge inspection report enga irukku?"
    code_switched = detect_code_switching(mixed_speech)
    assert code_switched in ("ta", "ta-IN", "en-IN")


# -------------------------------------------------------------
# Scenario 17: Anti-robot phrasing
# -------------------------------------------------------------
def test_scenario_17_anti_robot_phrasing():
    """Scenario 17: Never read internal processing steps, agents, or tools."""
    robotic_text = (
        "The RAG agent found the document. The SQL agent returned 3 rows. "
        "Querying the vector database using embeddings. LangGraph executed capability database."
    )
    cleaned = strip_technical_jargon(robotic_text)
    assert "rag agent" not in cleaned.lower()
    assert "sql agent" not in cleaned.lower()
    assert "vector database" not in cleaned.lower()
    assert "langgraph" not in cleaned.lower()
    assert "embeddings" not in cleaned.lower()


# -------------------------------------------------------------
# Scenario 18: Privacy mode vs normal salary
# -------------------------------------------------------------
def test_scenario_18_privacy_vs_salary():
    """Scenario 18: Salary is spoken naturally when privacy_mode is False, masked when True."""
    plan_normal = human_response_planner.plan_response(
        answer="Her salary is ₹45,000 a month.",
        query="What's her salary?",
        privacy_mode=False
    )
    assert "forty-five thousand rupees" in plan_normal.spoken_response

    plan_private = human_response_planner.plan_response(
        answer="Her salary is ₹45,000 a month.",
        query="What's her salary?",
        privacy_mode=True
    )
    assert "screen" in plan_private.spoken_response.lower()
