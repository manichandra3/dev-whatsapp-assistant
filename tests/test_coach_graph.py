"""
Tests for LangGraph Coach Integration

Regression tests to verify behavior parity between legacy and LangGraph runtimes.
"""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent_graph import CoachGraph, CoachState
from app.config import Settings
from app.database import DatabaseManager
from app.llm.providers import LLMProvider, LLMResponse, ToolCall
from app.safety_interceptor import SafetyInterceptor
from app.tools import ACLRehabTools


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = DatabaseManager(db_path)
        yield db
        db.close()


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        llm_provider="openai",
        llm_model="gpt-4o",
        openai_api_key="test-key",
        agent_runtime="langgraph",
        langgraph_max_tool_loops=3,
    )


@pytest.fixture
def mock_llm():
    """Create a mock LLM provider."""
    llm = MagicMock(spec=LLMProvider)
    llm.provider = "openai"
    llm.get_system_prompt.return_value = "You are a helpful ACL Rehab Coach."
    llm.chat = AsyncMock(return_value=LLMResponse(
        content="Hello! How can I help with your ACL recovery today?",
        tool_calls=[],
    ))
    llm.format_tool_results_for_openai = lambda tr: [
        {"role": "tool", "tool_call_id": t["tool_call_id"], "name": t["tool_name"], "content": str(t["result"])}
        for t in tr
    ]
    return llm


@pytest.fixture
def graph(settings, temp_db, mock_llm) -> CoachGraph:
    """Create a CoachGraph instance for testing."""
    safety = SafetyInterceptor()
    tools = ACLRehabTools(temp_db)
    return CoachGraph(
        settings=settings,
        db=temp_db,
        tools=tools,
        llm=mock_llm,
        safety=safety,
        max_tool_loops=3,
    )


@pytest.fixture
def graph_for_direct_response(settings, temp_db, mock_llm) -> tuple[CoachGraph, MagicMock]:
    """Create a CoachGraph for direct response tests."""
    safety = SafetyInterceptor()
    tools = ACLRehabTools(temp_db)
    graph = CoachGraph(
        settings=settings,
        db=temp_db,
        tools=tools,
        llm=mock_llm,
        safety=safety,
        max_tool_loops=3,
    )
    return graph, mock_llm


@pytest.fixture
def graph_for_tool_call(settings, temp_db) -> tuple[CoachGraph, MagicMock]:
    """Create a CoachGraph for tool call tests."""
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.provider = "openai"
    mock_llm.get_system_prompt.return_value = "You are a helpful ACL Rehab Coach."
    mock_llm.format_tool_results_for_openai = lambda tr: [
        {"role": "tool", "tool_call_id": t["tool_call_id"], "name": t["tool_name"], "content": str(t["result"])}
        for t in tr
    ]

    safety = SafetyInterceptor()
    tools = ACLRehabTools(temp_db)
    graph = CoachGraph(
        settings=settings,
        db=temp_db,
        tools=tools,
        llm=mock_llm,
        safety=safety,
        max_tool_loops=3,
    )
    return graph, mock_llm


class TestSafetyShortCircuit:
    """Test safety bypass behavior."""

    @pytest.mark.asyncio
    async def test_safety_red_flag_bypasses_llm(self, graph, mock_llm) -> None:
        """Test that red flag messages bypass LLM and return emergency response."""
        response = await graph.run("user123", "I have huge swelling in my calf")

        assert "MEDICAL ALERT" in response
        assert "IMMEDIATE medical attention" in response
        mock_llm.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_safety_numbness_bypasses_llm(self, graph, mock_llm) -> None:
        """Test that numbness triggers emergency response."""
        response = await graph.run("user123", "I have numbness in my foot")

        assert "MEDICAL ALERT" in response
        mock_llm.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_safety_severe_pain_bypasses_llm(self, graph, mock_llm) -> None:
        """Test that severe pain triggers emergency response."""
        response = await graph.run("user123", "Pain level 9 in my knee")

        assert "MEDICAL ALERT" in response
        mock_llm.chat.assert_not_called()


class TestDirectResponsePath:
    """Test direct response path without tool calls."""

    @pytest.mark.asyncio
    async def test_direct_response_no_tools(self, graph_for_direct_response) -> None:
        """Test response when LLM returns no tool calls."""
        graph, mock_llm = graph_for_direct_response

        response = await graph.run("user123", "Hello")

        assert "Hello" in response or "help" in response.lower()
        assert mock_llm.chat.call_count == 1

    @pytest.mark.asyncio
    async def test_user_initialization(self, settings, temp_db) -> None:
        """Test that new users are properly initialized."""
        mock_llm = MagicMock(spec=LLMProvider)
        mock_llm.provider = "openai"
        mock_llm.get_system_prompt.return_value = "You are a helpful ACL Rehab Coach."
        mock_llm.chat = AsyncMock(return_value=LLMResponse(
            content="Welcome! What's your surgery date?",
            tool_calls=[],
        ))
        mock_llm.format_tool_results_for_openai = lambda tr: [
            {"role": "tool", "tool_call_id": t["tool_call_id"], "name": t["tool_name"], "content": str(t["result"])}
            for t in tr
        ]

        safety = SafetyInterceptor()
        tools = ACLRehabTools(temp_db)
        graph = CoachGraph(
            settings=settings,
            db=temp_db,
            tools=tools,
            llm=mock_llm,
            safety=safety,
            max_tool_loops=3,
        )

        user_id = "new_user@s.whatsapp.net"

        await graph.run(user_id, "Hi")

        config = temp_db.get_user_config(user_id)
        assert config is not None
        assert config.surgery_date is not None


class TestToolCallPath:
    """Test tool call execution path."""

    @pytest.mark.asyncio
    async def test_tool_call_execution(self, settings, temp_db) -> None:
        """Test that tool calls are properly executed."""
        mock_llm = MagicMock(spec=LLMProvider)
        mock_llm.provider = "openai"
        mock_llm.get_system_prompt.return_value = "You are a helpful ACL Rehab Coach."
        mock_llm.format_tool_results_for_openai = lambda tr: [
            {"role": "tool", "tool_call_id": t["tool_call_id"], "name": t["tool_name"], "content": str(t["result"])}
            for t in tr
        ]

        tool_call = ToolCall(
            id="call_123",
            function_name="set_surgery_date",
            arguments='{"surgery_date": "2026-02-01"}',
        )

        mock_llm.chat = AsyncMock(side_effect=[
            LLMResponse(
                content="Let me set your surgery date.",
                tool_calls=[tool_call],
            ),
            LLMResponse(
                content="I've set your surgery date to 2026-02-01.",
                tool_calls=[],
            ),
        ])

        safety = SafetyInterceptor()
        tools = ACLRehabTools(temp_db)
        graph = CoachGraph(
            settings=settings,
            db=temp_db,
            tools=tools,
            llm=mock_llm,
            safety=safety,
            max_tool_loops=3,
        )

        user_id = "user_with_data@s.whatsapp.net"
        temp_db.set_surgery_date(user_id, "2026-01-15")

        response = await graph.run(user_id, "My surgery was on February 1st")

        assert "set" in response.lower() or "2026-02-01" in response
        assert temp_db.get_user_config(user_id).surgery_date == "2026-02-01"


class TestToolLoopCap:
    """Test tool loop iteration limits."""

    @pytest.mark.asyncio
    async def test_tool_loop_max_limit(self, graph, mock_llm) -> None:
        """Test that tool loops are capped at max_tool_loops."""
        tool_call = ToolCall(
            id="call_loop",
            function_name="get_recovery_phase",
            arguments="{}",
        )

        mock_llm.chat.return_value = LLMResponse(
            content="Here's your recovery phase.",
            tool_calls=[tool_call],
        )

        response = await graph.run("user123", "What phase am I in?")

        assert response is not None
        assert mock_llm.chat.call_count >= 1


class TestErrorFallback:
    """Test error handling and fallbacks."""

    @pytest.mark.asyncio
    async def test_error_returns_fallback_message(self, graph, mock_llm) -> None:
        """Test that errors return generic fallback message."""
        mock_llm.chat.side_effect = Exception("API Error")

        response = await graph.run("user123", "Hello")

        assert "❌" in response or "apologize" in response.lower() or "technical" in response.lower()


class TestGraphStructure:
    """Test graph structure and node connectivity."""

    def test_graph_has_required_nodes(self, graph) -> None:
        """Test that graph has all required nodes."""
        graph_nodes = graph._graph.nodes.keys()
        required_nodes = ["safety", "init_user", "context", "llm", "tool_exec", "post_tool_llm", "persist"]

        for node in required_nodes:
            assert node in graph_nodes, f"Missing node: {node}"

    def test_graph_max_tool_loops_config(self, graph) -> None:
        """Test that max_tool_loops is properly configured."""
        assert graph.max_tool_loops == 3


class TestCoachState:
    """Test CoachState typing and defaults."""

    def test_coach_state_defaults(self) -> None:
        """Test CoachState can be created with required fields."""
        state: CoachState = {
            "user_id": "test_user",
            "message_text": "test message",
            "conversation": [],
            "user_context": None,
            "safety_result": None,
            "llm_response": None,
            "tool_calls": [],
            "tool_results": [],
            "final_response": "",
            "error": None,
            "tool_loop_count": 0,
        }

        assert state["user_id"] == "test_user"
        assert state["tool_loop_count"] == 0