"""
LangGraph-based Agent Orchestrator for ACL Rehab Coach.

This module implements the coaching workflow as a LangGraph state machine,
providing explicit control flow, better debugging, and reliable orchestration.
"""

import json
import logging
from datetime import date
from typing import Any, Literal, TypedDict

from app.config import Settings
from app.database import DatabaseManager
from app.llm.providers import LLMProvider, LLMResponse, ToolCall
from app.safety_interceptor import SafetyInterceptor, SafetyCheckResult
from app.tools import ACLRehabTools
from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)


class CoachState(TypedDict):
    """State passed through the coach graph."""

    user_id: str
    message_text: str
    conversation: list[dict[str, Any]]
    user_context: str | None
    safety_result: SafetyCheckResult | None
    llm_response: LLMResponse | None
    tool_calls: list[ToolCall]
    tool_results: list[dict[str, Any]]
    final_response: str
    error: str | None
    tool_loop_count: int


class CoachGraph:
    """LangGraph-based coach orchestrator."""

    def __init__(
        self,
        settings: Settings,
        db: DatabaseManager,
        tools: ACLRehabTools,
        llm: LLMProvider,
        safety: SafetyInterceptor,
        max_tool_loops: int = 3,
    ) -> None:
        self.settings = settings
        self.db = db
        self.tools = tools
        self.llm = llm
        self.safety = safety
        self.max_tool_loops = max_tool_loops
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        """Build the coaching state machine graph."""
        graph = StateGraph(CoachState)

        graph.add_node("safety", self._safety_node)
        graph.add_node("init_user", self._init_user_node)
        graph.add_node("context", self._context_node)
        graph.add_node("llm", self._llm_node)
        graph.add_node("tool_exec", self._tool_exec_node)
        graph.add_node("post_tool_llm", self._post_tool_llm_node)
        graph.add_node("persist", self._persist_node)

        graph.set_entry_point("safety")

        graph.add_conditional_edges(
            "safety",
            self._should_bypass,
            {
                "bypass": END,
                "continue": "init_user",
            },
        )

        graph.add_edge("init_user", "context")
        graph.add_edge("context", "llm")

        graph.add_conditional_edges(
            "llm",
            self._has_tool_calls,
            {
                "tools": "tool_exec",
                "direct": "persist",
            },
        )

        graph.add_conditional_edges(
            "tool_exec",
            self._should_continue_tools,
            {
                "continue": "post_tool_llm",
                "max_loops": "persist",
            },
        )

        graph.add_edge("post_tool_llm", "llm")

        graph.add_edge("persist", END)

        return graph.compile()

    def _should_bypass(self, state: CoachState) -> Literal["bypass", "continue"]:
        """Check if safety red flag detected."""
        safety_result = state.get("safety_result")
        if safety_result and safety_result.has_red_flag:
            return "bypass"
        return "continue"

    def _has_tool_calls(self, state: CoachState) -> Literal["tools", "direct"]:
        """Check if LLM response has tool calls or if there was an error."""
        if state.get("error"):
            return "direct"
        if state.get("tool_calls"):
            return "tools"
        return "direct"

    def _should_continue_tools(
        self, state: CoachState
    ) -> Literal["continue", "max_loops"]:
        """Check if tool loop should continue or terminate."""
        tool_loop_count = state.get("tool_loop_count", 0)
        if state.get("tool_calls") and tool_loop_count < self.max_tool_loops:
            return "continue"
        return "max_loops"

    def _safety_node(self, state: CoachState) -> CoachState:
        """Run safety interceptor."""
        logger.info(f"[GRAPH] Running safety check for {state['user_id']}")
        safety_result = self.safety.check_message(state["message_text"])
        state["safety_result"] = safety_result
        if safety_result.has_red_flag:
            state["final_response"] = safety_result.response or ""
            logger.warning(f"[GRAPH] Safety red flag detected for {state['user_id']}")
        return state

    def _init_user_node(self, state: CoachState) -> CoachState:
        """Initialize user if needed."""
        user_id = state["user_id"]
        logger.info(f"[GRAPH] Initializing user {user_id}")

        user_config = self.db.get_user_config(user_id)
        if not user_config:
            surgery_date = self.settings.surgery_date or date.today().isoformat()
            self.db.set_surgery_date(user_id, surgery_date)
            logger.info(f"[GRAPH] Created new user {user_id} with surgery date {surgery_date}")

        if not state.get("conversation"):
            state["conversation"] = [
                {"role": "system", "content": self.llm.get_system_prompt()}
            ]

        return state

    def _context_node(self, state: CoachState) -> CoachState:
        """Build user context and prepend to message."""
        user_id = state["user_id"]
        message_text = state["message_text"]

        user_context = self.tools.build_user_context(user_id)
        state["user_context"] = user_context

        if user_context:
            message_with_context = f"{user_context}\n\n---\nUser message: {message_text}"
        else:
            message_with_context = message_text

        state["conversation"].append({"role": "user", "content": message_with_context})
        return state

    async def _llm_node(self, state: CoachState) -> CoachState:
        """Call LLM with current conversation."""
        logger.info(f"[GRAPH] Calling LLM for {state['user_id']}")

        try:
            response = await self.llm.chat(
                state["conversation"], self.tools.get_tool_definitions()
            )
            state["llm_response"] = response
            state["tool_calls"] = response.tool_calls
            logger.info(f"[GRAPH] LLM returned {len(response.tool_calls)} tool calls")
        except Exception as e:
            logger.error(f"[GRAPH] LLM error: {e}")
            state["error"] = str(e)
            if not state.get("final_response"):
                err_msg = str(e)
                if self.llm.provider == "anthropic" and (
                    "Input should be a valid list" in err_msg
                    or 'Unexpected role "tool"' in err_msg
                ):
                    state["final_response"] = (
                        "❌ I hit a temporary formatting issue and recovered. "
                        "Please send your check-in once more."
                    )
                    state["conversation"] = [
                        {"role": "system", "content": self.llm.get_system_prompt()}
                    ]
                else:
                    state["final_response"] = (
                        "❌ I apologize, but I encountered a technical issue. "
                        "Please try sending your message again."
                    )

        return state

    async def _tool_exec_node(self, state: CoachState) -> CoachState:
        """Execute tool calls and format results."""
        user_id = state["user_id"]
        tool_calls = state.get("tool_calls", [])

        logger.info(f"[GRAPH] Executing {len(tool_calls)} tool calls")

        tool_results = []
        for tool_call in tool_calls:
            tool_name = tool_call.function_name
            tool_args = json.loads(tool_call.arguments)

            logger.info(f"[GRAPH] Executing tool: {tool_name} with args: {tool_args}")

            result = await self.tools.execute_tool(tool_name, user_id, tool_args)
            tool_results.append({
                "tool_call_id": tool_call.id,
                "tool_name": tool_name,
                "result": result,
            })

        state["tool_results"] = tool_results

        llm_response = state.get("llm_response")
        content = llm_response.content if llm_response else ""
        
        state["conversation"].append({
            "role": "assistant",
            "content": content or "",
            "tool_calls": [tc.to_dict() for tc in tool_calls],
        })

        if self.llm.provider == "anthropic":
            state["conversation"].append(
                self.llm.format_tool_results_for_anthropic(tool_results)
            )
        else:
            state["conversation"].extend(
                self.llm.format_tool_results_for_openai(tool_results)
            )

        state["tool_loop_count"] = state.get("tool_loop_count", 0) + 1

        return state

    async def _post_tool_llm_node(self, state: CoachState) -> CoachState:
        """Get final response from LLM after tool execution."""
        logger.info(f"[GRAPH] Getting post-tool LLM response for {state['user_id']}")

        try:
            final_response = await self.llm.chat(state["conversation"])
            state["llm_response"] = final_response
            state["final_response"] = final_response.content or ""
        except Exception as e:
            logger.error(f"[GRAPH] Post-tool LLM error: {e}")
            state["error"] = str(e)

        return state

    def _persist_node(self, state: CoachState) -> CoachState:
        """Update conversation history and set final response."""
        llm_response = state.get("llm_response")
        llm_content = llm_response.content if llm_response and llm_response.content else ""

        state["conversation"].append({"role": "assistant", "content": llm_content})

        max_messages = 20
        if len(state["conversation"]) > max_messages:
            system_msg = state["conversation"][0]
            state["conversation"] = [system_msg, *state["conversation"][-(max_messages - 1):]]

        if not state.get("final_response"):
            state["final_response"] = llm_content

        return state

    async def run(
        self,
        user_id: str,
        message_text: str,
        media_id: str | None = None,
        media: dict[str, Any] | None = None,
    ) -> str:
        """Run the graph and return the final response."""
        
        if media or media_id:
            media_parts = ["[MEDIA ATTACHED]"]
            if media:
                media_parts.append(f"Type: {media.get('content_type', 'unknown')}")
                media_parts.append(f"Filename: {media.get('filename', 'unknown')}")
                if media_id:
                    media_parts.append(f"Media ID: {media_id}")
                if media.get("caption"):
                    media_parts.append(f"Caption: {media.get('caption')}")
            elif media_id:
                media_parts.append(f"Media ID: {media_id}")
            message_text = f"{message_text}\n\n" + "\n".join(media_parts)

        initial_state: CoachState = {
            "user_id": user_id,
            "message_text": message_text,
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

        try:
            final_state = await self._graph.ainvoke(initial_state)
            return final_state.get("final_response", "")
        except Exception as e:
            logger.error(f"[GRAPH] Graph execution error: {e}")
            return (
                "❌ I apologize, but I encountered a technical issue. "
                "Please try sending your message again."
            )