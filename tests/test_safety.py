"""
Safety Interceptor Test Suite

Mirrors the test cases from src/test-safety.js
"""

import pytest

from app.safety_interceptor import SafetyInterceptor


@pytest.fixture
def safety() -> SafetyInterceptor:
    """Create a safety interceptor instance for testing."""
    return SafetyInterceptor()


# Test cases mirrored from src/test-safety.js
TEST_CASES = [
    pytest.param(
        "My pain level is 4 today and swelling is about the same",
        False,
        id="Normal message",
    ),
    pytest.param(
        "I have some calf pain in my leg",
        True,
        id="Calf pain (DVT indicator)",
    ),
    pytest.param(
        "I think I have a fever, feeling really hot",
        True,
        id="Fever (infection indicator)",
    ),
    pytest.param(
        "I heard a loud pop in my knee during exercise",
        True,
        id="Loud pop (graft failure)",
    ),
    pytest.param(
        "The swelling is huge and getting worse",
        True,
        id="Huge swelling",
    ),
    pytest.param(
        "I have severe pain that won't go away",
        True,
        id="Severe pain",
    ),
    pytest.param(
        "My foot feels numb and tingly",
        True,
        id="Numbness",
    ),
    pytest.param(
        "Having chest pain and hard to breathe",
        True,
        id="Chest pain",
    ),
    pytest.param(
        "My pain level is 9 out of 10",
        True,
        id="Pain level 9",
    ),
    pytest.param(
        "Pain is about 6 today",
        False,
        id="Normal high pain",
    ),
    pytest.param(
        "Worried about infection, seeing some discharge",
        True,
        id="Infection mention",
    ),
    pytest.param(
        "Still have some swelling but it's better",
        False,
        id="General swelling",
    ),
]


@pytest.mark.parametrize("message,should_trigger", TEST_CASES)
def test_safety_check(safety: SafetyInterceptor, message: str, should_trigger: bool) -> None:
    """Test that safety interceptor correctly identifies red flag messages."""
    result = safety.check_message(message)
    assert result.has_red_flag == should_trigger, (
        f"Message '{message}' expected has_red_flag={should_trigger}, "
        f"got {result.has_red_flag}"
    )


def test_empty_message(safety: SafetyInterceptor) -> None:
    """Test that empty messages don't trigger red flags."""
    result = safety.check_message("")
    assert result.has_red_flag is False
    assert result.response is None


def test_none_message(safety: SafetyInterceptor) -> None:
    """Test that None messages don't trigger red flags."""
    result = safety.check_message(None)  # type: ignore[arg-type]
    assert result.has_red_flag is False
    assert result.response is None


def test_red_flag_returns_emergency_response(safety: SafetyInterceptor) -> None:
    """Test that red flags return the emergency response."""
    result = safety.check_message("I have severe pain")
    assert result.has_red_flag is True
    assert result.response is not None
    assert "MEDICAL ALERT" in result.response
    assert "CONTACT YOUR SURGEON" in result.response


def test_red_flag_returns_matched_pattern(safety: SafetyInterceptor) -> None:
    """Test that red flags include the matched pattern."""
    result = safety.check_message("I have numbness in my leg")
    assert result.has_red_flag is True
    assert result.matched_pattern is not None
    assert "numbness" in result.matched_pattern


def test_case_insensitivity(safety: SafetyInterceptor) -> None:
    """Test that pattern matching is case-insensitive."""
    lower_result = safety.check_message("i have severe pain")
    upper_result = safety.check_message("I HAVE SEVERE PAIN")
    mixed_result = safety.check_message("I Have Severe Pain")

    assert lower_result.has_red_flag is True
    assert upper_result.has_red_flag is True
    assert mixed_result.has_red_flag is True


def test_get_patterns(safety: SafetyInterceptor) -> None:
    """Test that patterns can be retrieved."""
    patterns = safety.get_patterns()
    assert len(patterns) > 0
    assert all(hasattr(p, "pattern") for p in patterns)


def test_test_pattern(safety: SafetyInterceptor) -> None:
    """Test the test_pattern helper method."""
    patterns = safety.get_patterns()
    # First pattern should match "calf pain"
    assert safety.test_pattern("calf pain", patterns[0]) is True
    assert safety.test_pattern("normal message", patterns[0]) is False
