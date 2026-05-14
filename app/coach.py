"""
ACL Rehab Coach - Main Conversation Orchestrator

Coordinates safety interceptor, LLM, and tools to handle user messages.
Manages conversation history and implements the core coaching workflow.
"""

import json
import logging
from datetime import date
from typing import Any

from app.agent_graph import CoachGraph
from app.config import Settings
from app.database import DatabaseManager
from app.llm.providers import LLMProvider
from app.safety_interceptor import SafetyInterceptor
from app.tools import ACLRehabTools
from app.onboarding import OnboardingManager

logger = logging.getLogger(__name__)


class ACLRehabCoach:
    """
    Main orchestrator for the ACL Rehab Coach.

    Implements the message handling flow:
    1. Safety check (before LLM)
    2. User initialization
    3. LLM call with tools
    4. Tool execution
    5. Final response
    """

    # Error messages - exact same text as Node.js for behavior parity
    FORMAT_RECOVERY_MESSAGE = (
        "❌ I hit a temporary formatting issue and recovered. "
        "Please send your check-in once more."
    )
    GENERIC_ERROR_MESSAGE = (
        "❌ I apologize, but I encountered a technical issue. "
        "Please try sending your message again."
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.conversations: dict[str, list[dict[str, Any]]] = {}

        # Initialize components
        self.safety = SafetyInterceptor()
        self.db = DatabaseManager(settings.database_path)
        # Initialize LLM first so we can pass it to tools
        self.llm = LLMProvider(
            provider=settings.llm_provider,
            model=settings.llm_model,
            api_key=settings.get_llm_api_key(),
        )

        self.tools = ACLRehabTools(self.db, self.llm)
        self.onboarding = OnboardingManager(self.db)
        
        from app.media import MediaManager
        self.media_manager = MediaManager(self.db)

        # Initialize LangGraph if enabled
        self.agent_graph: CoachGraph | None = None
        if settings.agent_runtime == "langgraph":
            self.agent_graph = CoachGraph(
                settings=settings,
                db=self.db,
                tools=self.tools,
                llm=self.llm,
                safety=self.safety,
                max_tool_loops=settings.langgraph_max_tool_loops,
            )
            logger.info(f"[COACH] Initialized with LangGraph runtime (max_tool_loops={settings.langgraph_max_tool_loops})")
        else:
            logger.info(f"[COACH] Initialized with legacy runtime (provider: {settings.llm_provider})")

    async def handle_message(
        self,
        user_id: str,
        message_text: str,
        media: dict[str, Any] | None = None,
    ) -> str | tuple[str, dict[str, Any]]:
        """
        Handle an incoming message from a user.

        Args:
            user_id: WhatsApp user ID (format: <number>@s.whatsapp.net)
            message_text: The message content

        Returns:
            Response text to send back to the user
        """
        # Save media if present
        media_id = None
        if media:
            try:
                media_id = self.media_manager.save_media(user_id, media)
                logger.info(f"[COACH] Saved media with ID: {media_id}")
            except Exception as e:
                logger.error(f"[COACH] Error saving media: {e}")

        # STEP 0: Safety Interceptor (ALWAYS FIRST - BEFORE ONBOARDING)
        safety_check = self.safety.check_message(message_text)
        if safety_check.has_red_flag:
            logger.warning("[SAFETY] RED FLAG DETECTED - Sending emergency response")
            return safety_check.response  # type: ignore

        # STEP 1: Onboarding Interceptor
        onboarding_response = self.onboarding.handle_message(user_id, message_text)
        if onboarding_response:
            return onboarding_response

        # Use LangGraph if enabled
        if self.agent_graph is not None:
            return await self.agent_graph.run(user_id, message_text, media_id=media_id)

        # Legacy implementation
        return await self._handle_message_legacy(user_id, message_text, media, media_id)

    async def _handle_message_legacy(
        self,
        user_id: str,
        message_text: str,
        media: dict[str, Any] | None,
        media_id: str | None = None,
    ) -> str:
        logger.info(f"[COACH] Processing message from {user_id}")

        # STEP 2: Initialize user if needed
        await self._initialize_user(user_id)

        try:
            # STEP 3: Get conversation history
            messages = self._get_conversation_history(user_id)

            # STEP 4: Build user context and prepend to message
            user_context = self.tools.build_user_context(user_id)
            message_with_context = message_text
            if user_context:
                message_with_context = f"{user_context}\n\n---\nUser message: {message_text}"
            if media:
                media_info = [
                    "[MEDIA ATTACHED]",
                    f"Type: {media.get('content_type', 'unknown')}",
                    f"Filename: {media.get('filename', 'unknown')}",
                ]
                if media_id:
                    media_info.append(f"Media ID: {media_id}")
                if media.get("caption"):
                    media_info.append(f"Caption: {media.get('caption')}")
                
                message_with_context = f"{message_with_context}\n\n" + "\n".join(media_info)

            # Add new user message with context
            messages.append({"role": "user", "content": message_with_context})

            # STEP 4: Call LLM with tools
            response = await self.llm.chat(
                messages, self.tools.get_tool_definitions()
            )

            # STEP 5: Handle tool calls
            if response.tool_calls:
                logger.info(
                    f"[COACH] Processing {len(response.tool_calls)} tool calls"
                )

                tool_results = []

                for tool_call in response.tool_calls:
                    tool_name = tool_call.function_name
                    tool_args = json.loads(tool_call.arguments)

                    logger.info(f"[TOOL] Executing: {tool_name} with args: {tool_args}")

                    result = await self.tools.execute_tool(
                        tool_name, user_id, tool_args
                    )
                    tool_results.append({
                        "tool_call_id": tool_call.id,
                        "tool_name": tool_name,
                        "result": result,
                    })

                # Add assistant message with tool calls to history
                messages.append({
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": [tc.to_dict() for tc in response.tool_calls],
                })

                # Add tool results to history (format depends on provider)
                if self.llm.provider == "anthropic":
                    messages.append(
                        self.llm.format_tool_results_for_anthropic(tool_results)
                    )
                else:
                    messages.extend(
                        self.llm.format_tool_results_for_openai(tool_results)
                    )

                # Get final response from LLM after tool execution
                final_response = await self.llm.chat(messages)

                # Update conversation history
                messages.append({
                    "role": "assistant",
                    "content": final_response.content,
                })

                self._update_conversation_history(user_id, messages)
                return final_response.content or ""

            else:
                # No tool calls - direct response
                messages.append({
                    "role": "assistant",
                    "content": response.content,
                })

                self._update_conversation_history(user_id, messages)
                return response.content or ""

        except Exception as e:
            logger.error(f"[COACH] Error processing message: {e}")

            # Auto-heal for Anthropic format errors (same behavior as Node.js)
            err_msg = str(e)
            if self.llm.provider == "anthropic" and (
                "Input should be a valid list" in err_msg
                or 'Unexpected role "tool"' in err_msg
            ):
                logger.warning(
                    f"[COACH] Resetting conversation history for {user_id} "
                    "due to Anthropic format error"
                )
                self.conversations[user_id] = [
                    {"role": "system", "content": self.llm.get_system_prompt()}
                ]
                return self.FORMAT_RECOVERY_MESSAGE

            return self.GENERIC_ERROR_MESSAGE

    async def _initialize_user(self, user_id: str) -> None:
        """Initialize user if they don't exist."""
        user_config = self.db.get_user_config(user_id)

        if not user_config:
            # We shouldn't hit this if onboarding is enabled and working,
            # but keep it as a fallback.
            surgery_date = (
                self.settings.surgery_date
                or date.today().isoformat()
            )

            self.db.set_surgery_date(user_id, surgery_date)
            logger.info(
                f"[COACH] Initialized new user (fallback): {user_id} "
                f"with surgery date: {surgery_date}"
            )

            # Initialize conversation with system prompt
            self.conversations[user_id] = [
                {"role": "system", "content": self.llm.get_system_prompt()}
            ]

        elif user_id not in self.conversations:
            # User exists but no conversation history - initialize
            self.conversations[user_id] = [
                {"role": "system", "content": self.llm.get_system_prompt()}
            ]

    def _get_conversation_history(self, user_id: str) -> list[dict[str, Any]]:
        """Get conversation history for a user."""
        if user_id in self.conversations:
            # Return a copy to avoid modifying the stored history directly
            return list(self.conversations[user_id])

        return [{"role": "system", "content": self.llm.get_system_prompt()}]

    def _update_conversation_history(
        self, user_id: str, messages: list[dict[str, Any]]
    ) -> None:
        """Update conversation history, keeping last 20 messages."""
        max_messages = 20

        if len(messages) > max_messages:
            # Always keep system message
            system_msg = messages[0]
            recent_messages = messages[-(max_messages - 1) :]
            self.conversations[user_id] = [system_msg, *recent_messages]
        else:
            self.conversations[user_id] = messages

    def close(self) -> None:
        """Clean up resources."""
        self.db.close()
        logger.info("[COACH] Shutdown complete")
