"""
Safety Interceptor - Red Flag Detection System

This module implements the deterministic safety rule engine that intercepts
all incoming messages BEFORE LLM processing. If red flag keywords are detected,
it bypasses the AI and returns a hardcoded emergency response.
"""

import re
from dataclasses import dataclass


@dataclass
class SafetyCheckResult:
    """Result of a safety check on a message."""

    has_red_flag: bool
    response: str | None
    matched_pattern: str | None = None


class SafetyInterceptor:
    """
    Deterministic safety interceptor that checks messages for medical red flags.

    Red flags trigger an immediate emergency response without LLM involvement.
    """

    def __init__(self) -> None:
        # Critical medical emergency keywords - exact same patterns as Node.js
        self.red_flag_patterns: list[re.Pattern[str]] = [
            # DVT/Blood clot indicators
            re.compile(r"\b(calf\s+pain|calf\s+swelling|calf\s+tenderness)\b", re.IGNORECASE),
            # Infection indicators
            re.compile(
                r"\b(fever|high\s+fever|temperature|chills|infection|pus|discharge|oozing)\b",
                re.IGNORECASE,
            ),
            # Graft failure indicators
            re.compile(
                r"\b(loud\s+pop|popping\s+sound|heard\s+pop|graft\s+failure|knee\s+gave\s+out)\b",
                re.IGNORECASE,
            ),
            # Severe swelling
            re.compile(
                r"\b(huge\s+swelling|massive\s+swelling|extreme\s+swelling|swelling\s+worse|excessive\s+swelling)\b"
                r"|\bswelling\b.{0,30}\b(huge|massive|extreme|excessive)\b"
                r"|\b(huge|massive|extreme|excessive)\b.{0,30}\bswelling\b",
                re.IGNORECASE,
            ),
            # Severe pain
            re.compile(
                r"\b(severe\s+pain|unbearable\s+pain|excruciating|pain\s+level\s+(is\s+)?(9|10)|worst\s+pain)\b",
                re.IGNORECASE,
            ),
            # Neurological symptoms
            re.compile(
                r"\b(numbness|numb|tingling|tingly|loss\s+of\s+feeling|can't\s+feel|nerve\s+damage)\b",
                re.IGNORECASE,
            ),
            # Cardiovascular/respiratory emergencies
            re.compile(
                r"\b(chest\s+pain|breathing\s+difficult|shortness\s+of\s+breath|can't\s+breathe)\b",
                re.IGNORECASE,
            ),
            # Circulation issues
            re.compile(r"\b(foot\s+cold|foot\s+blue|toes\s+blue|no\s+pulse)\b", re.IGNORECASE),
        ]

        # Emergency response - exact same text as Node.js
        self.emergency_response = """🚨 **MEDICAL ALERT** 🚨

I've detected symptoms that require IMMEDIATE medical attention. 

**DO NOT WAIT - CONTACT YOUR SURGEON OR GO TO THE ER NOW**

⚠️ Potential emergency indicators detected:
- Deep vein thrombosis (blood clot)
- Infection
- Graft failure
- Severe complications

📞 **Actions to take RIGHT NOW:**
1. Call your surgeon's emergency line
2. If unavailable, go to the Emergency Room
3. If experiencing chest pain or breathing difficulty, call emergency services (911)

⏰ **Time is critical** - these symptoms can indicate life-threatening complications.

This is an automated safety alert. I cannot provide medical diagnosis or treatment. Please seek immediate professional medical care."""

    def check_message(self, message: str) -> SafetyCheckResult:
        """
        Check message for red flag keywords.

        Args:
            message: The incoming user message

        Returns:
            SafetyCheckResult with has_red_flag, response, and matched_pattern
        """
        if not message:
            return SafetyCheckResult(has_red_flag=False, response=None)

        lower_message = message.lower()

        for pattern in self.red_flag_patterns:
            if pattern.search(lower_message):
                return SafetyCheckResult(
                    has_red_flag=True,
                    response=self.emergency_response,
                    matched_pattern=pattern.pattern,
                )

        return SafetyCheckResult(has_red_flag=False, response=None)

    def get_patterns(self) -> list[re.Pattern[str]]:
        """Get all red flag patterns (for testing/debugging)."""
        return self.red_flag_patterns

    def test_pattern(self, text: str, pattern: re.Pattern[str]) -> bool:
        """Test a specific pattern against text."""
        return bool(pattern.search(text.lower()))
