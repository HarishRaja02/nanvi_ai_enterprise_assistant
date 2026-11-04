"""Interruption arbitrator: distinguishes between false interrupts (backchannels, coughs,
fillers, silence, acoustic speaker echoes, continue signals) and valid interrupts (queries, commands, corrections).
"""
from __future__ import annotations

import enum
import re
from typing import Optional


class InterruptionDecision(str, enum.Enum):
    RESUME = "resume"              # False interrupt -> resume playback of paused response
    CUT_AND_RESPOND = "cut_and_respond"  # Valid interrupt -> discard remainder, respond to new input
    HOLD = "hold"                  # Explicit hold ("wait", "hold on") -> stay paused


# Common conversational listening cues / backchannels in spoken dialogue
BACKCHANNEL_WORDS = {
    # Affirmative / acknowledgment
    "yeah", "yeh", "ya", "yea", "yes", "yep", "yup", "aye",
    "uh-huh", "uhhuh", "uh-hum", "mhm", "mm-hmm", "mmhmm", "mm", "mmm", "hmm", "hm",
    "ok", "okay", "k", "right", "alright", "all right", "sure", "cool", "fine",
    "got it", "gotcha", "true", "great", "nice", "agreed", "understood",
    # Reactions / fillers
    "ah", "oh", "um", "uh", "er", "ha", "haha", "hahaha", "wow",
    "i see", "makes sense", "no problem",
}

# Explicit continue signals
_CONTINUE_PATTERN = re.compile(
    r"^\s*(ok(ay)?[, ]+)?(please\s+)?(continue|go on|keep going|carry on|go ahead|resume|proceed)\b[\s.!]*$",
    re.I,
)

# Explicit hold signals ("wait", "hold on", "give me a sec") without a follow-up query
_HOLD_PATTERN = re.compile(
    r"^\s*(please\s+)?(wait|hold on|hang on|give me a sec(ond)?|one sec(ond)?|just a sec(ond)?|hold up)[\s.!]*$",
    re.I,
)

# Noise / cough / artifact tokens from STT engines
_NOISE_TOKENS = {
    "[cough]", "[laughter]", "[applause]", "[snort]", "[music]", "[sigh]",
    "*cough*", "*clears throat*", "(cough)", "(clears throat)", "(laughter)",
}


class InterruptionArbitrator:
    """Evaluates whether an incoming user utterance during speech is a real interruption
    or a false interrupt / backchannel / speaker echo.
    """

    @classmethod
    def is_continue(cls, text: str) -> bool:
        return bool(_CONTINUE_PATTERN.match(text.strip()))

    @classmethod
    def is_hold(cls, text: str) -> bool:
        return bool(_HOLD_PATTERN.match(text.strip()))

    @classmethod
    def is_noise(cls, text: str) -> bool:
        cleaned = text.strip().lower()
        if not cleaned:
            return True
        if cleaned in _NOISE_TOKENS:
            return True
        # Strings with only punctuation/symbols
        if re.match(r"^[\s\.\,\?\!\;\:\-\_\(\)\[\]\*]+$", cleaned):
            return True
        return False

    @classmethod
    def is_backchannel(cls, text: str) -> bool:
        cleaned = re.sub(r"[^\w\s-]", "", text.strip().lower())
        words = cleaned.split()
        if not words:
            return True
        # If the whole phrase is in backchannels
        if cleaned in BACKCHANNEL_WORDS:
            return True
        # If every word is a backchannel word (e.g. "yeah okay", "uh-huh yeah", "right got it")
        if all(w in BACKCHANNEL_WORDS for w in words):
            return True
        return False

    @classmethod
    def is_echo(cls, text: str, agent_text: Optional[str]) -> bool:
        """Detect whether text is an acoustic echo of the agent's own speech (laptop speaker bleed)."""
        if not text or not agent_text:
            return False
        t_clean = re.sub(r"[^\w\s]", "", text.strip().lower())
        a_clean = re.sub(r"[^\w\s]", "", agent_text.strip().lower())
        if not t_clean or not a_clean:
            return False
        # Direct substring match (e.g. mic captured a whole phrase the agent spoke)
        if len(t_clean) >= 6 and (t_clean in a_clean or a_clean in t_clean):
            return True
        t_words = [w for w in t_clean.split() if len(w) > 2]
        if not t_words:
            return False
        a_words = set(a_clean.split())
        matches = sum(1 for w in t_words if w in a_words)
        return (matches / len(t_words)) >= 0.45

    @classmethod
    def classify(cls, text: str, agent_text: Optional[str] = None) -> InterruptionDecision:
        """Classify user text into RESUME (false interrupt/echo), HOLD, or CUT_AND_RESPOND."""
        text = text.strip()

        # 1. Empty or pure noise / coughs / artifacts -> False interrupt -> RESUME
        if cls.is_noise(text):
            return InterruptionDecision.RESUME

        # 2. Acoustic speaker echo (mic hearing laptop speaker) -> False interrupt -> RESUME
        if agent_text and cls.is_echo(text, agent_text):
            return InterruptionDecision.RESUME

        # 3. Explicit continue -> RESUME
        if cls.is_continue(text):
            return InterruptionDecision.RESUME

        # 4. Explicit hold ("wait", "hold on") without additional question -> HOLD
        if cls.is_hold(text):
            return InterruptionDecision.HOLD

        # 5. Conversational backchannel ("yeah", "uh-huh", "mhm", "ok") -> False interrupt -> RESUME
        if cls.is_backchannel(text):
            return InterruptionDecision.RESUME

        # 6. Otherwise, this is a VALID interruption (question, instruction, correction, topic change)
        return InterruptionDecision.CUT_AND_RESPOND
