"""Unit tests for Milestone 4: Human Response Planner, Spoken Number Formatter, and Phrase Pools."""

from backend.chat.response_planner import (
    SpokenNumberFormatter,
    PhrasePool,
    HumanResponsePlanner,
    human_response_planner,
)


def test_spoken_number_formatter_indian_currency():
    """Verify Indian currency formatting with crores, lakhs, and abbreviations."""
    # Crores
    res1 = SpokenNumberFormatter.format("Total sales reached ₹18,40,00,000 this fiscal year.")
    assert "18.4 crore rupees" in res1
    assert "18,40,00,000" not in res1

    # Lakhs
    res2 = SpokenNumberFormatter.format("Infrastructure expenses were ₹12,00,000.")
    assert "12 lakh rupees" in res2

    # Abbreviations
    res3 = SpokenNumberFormatter.format("Q2 budget is ₹15.5 Cr while marketing is ₹2.3L.")
    assert "15.5 crore rupees" in res3
    assert "2.3 lakh rupees" in res3


def test_spoken_number_formatter_western_currency_and_percentages():
    """Verify dollar abbreviations and percentage conversions."""
    res1 = SpokenNumberFormatter.format("Revenue was $4.2M, up by 14.2% YoY.")
    assert "4.2 million dollars" in res1
    assert "about 14 percent" in res1
    assert "year over year" in res1

    res2 = SpokenNumberFormatter.format("Enterprise contract signed for $5B.")
    assert "5 billion dollars" in res2

    res3 = SpokenNumberFormatter.format("Net margin was 15%.")
    assert "15 percent" in res3


def test_spoken_number_formatter_calendar_year_preservation():
    """Calendar years (e.g. 2024, 2025) must remain natural numbers, not lakhs/crores."""
    res = SpokenNumberFormatter.format("In 2024, the company expanded operations to FY 2025.")
    assert "2024" in res
    assert "Fiscal Year 2025" in res


def test_phrase_pool_never_repeats_back_to_back():
    """Verify that PhrasePool generates varied non-identical phrases sequentially."""
    pool = PhrasePool()
    categories = ["KNOWLEDGE_SEARCH", "SQL_QUERY", "EMAIL_SEARCH", "WEB_SEARCH", "INTERMEDIATE_UPDATE"]

    for cat in categories:
        seen = []
        for _ in range(10):
            phrase = pool.get_phrase(cat)
            assert len(phrase) > 5
            if seen:
                # Must never repeat identically back to back
                assert phrase != seen[-1], f"Phrase repeated consecutively for {cat}: {phrase}"
            seen.append(phrase)


def test_human_response_planner_conclusion_first_and_strips_disclaimers():
    """Verify conclusion-first delivery and total elimination of AI disclaimers and tables."""
    raw_answer = """
According to the retrieved documents, total enterprise revenue for Q3 increased by 14% to $4.2M.

| Division | Revenue | Growth |
| Enterprise | $3.2M | +18% |
| SMB | $1.0M | +2% |

As an AI, I should note that details can be reviewed in contract [Source 1].
In summary, enterprise is driving most of the momentum.
"""
    plan = human_response_planner.plan_response(
        answer=raw_answer,
        query="What was our Q3 revenue?",
    )

    # 1. Spoken response must be conclusion-first
    assert plan.spoken_response.startswith("Total enterprise revenue for Quarter 3 increased")
    # 2. Must NEVER contain AI disclaimers or tables
    assert "According to the retrieved documents" not in plan.spoken_response
    assert "As an AI" not in plan.spoken_response
    assert "In summary" not in plan.spoken_response
    assert "|" not in plan.spoken_response
    assert "[Source 1]" not in plan.spoken_response
    # 3. Must expand numbers
    assert "4.2 million dollars" in plan.spoken_response
    # 4. Must provide clean screen message
    assert "screen" in plan.screen_message.lower() or "displayed" in plan.screen_message.lower()
    # 5. Must provide relevant suggested actions
    assert len(plan.suggested_actions) >= 2


def test_human_response_planner_adaptive_verbosity():
    """Verify verbosity adaptation: concise when requested, expanded when detailed requested."""
    multi_sentence = "Revenue grew 14%. Enterprise was the top driver. SMB retained 98% of clients. Profit reached $1.2M."

    short_plan = human_response_planner.plan_response(
        answer=multi_sentence,
        query="Revenue overview",
        verbosity_preference="short",
    )
    # 1 sentence when short requested
    assert len(short_plan.spoken_response.split(".")) <= 2

    long_plan = human_response_planner.plan_response(
        answer=multi_sentence,
        query="Revenue overview",
        verbosity_preference="detailed",
    )
    # Multi-sentence when detailed requested
    assert len(long_plan.spoken_response.split(".")) >= 3


def test_human_response_planner_uncertainty_handling():
    """Verify honest uncertainty framing when evidence contains low confidence indicators."""
    uncertain_answer = "The exact figures for August are approximate and not entirely sure."
    plan = human_response_planner.plan_response(
        answer=uncertain_answer,
        query="Show August sales",
    )
    assert plan.confidence_level == "moderate"
    assert "not fully sure" in plan.spoken_response.lower()
