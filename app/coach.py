"""
ACL Rehab Coach - Main Conversation Orchestrator

Coordinates safety interceptor, LLM, and tools to handle user messages.
Manages conversation history and implements the core coaching workflow.
"""

import json
import logging
from datetime import date, datetime
from typing import Any

from app.config import Settings
from app.database import DatabaseManager
from app.llm.providers import LLMProvider, LLMResponse, ToolCall
from app.safety_interceptor import SafetyInterceptor
from app.tools import ACLRehabTools

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
        self.tools = ACLRehabTools(self.db)
        self.llm = LLMProvider(
            provider=settings.llm_provider,
            model=settings.llm_model,
            api_key=settings.get_llm_api_key(),
        )

        logger.info(f"[COACH] Initialized with provider: {settings.llm_provider}")

    async def handle_message(self, user_id: str, message_text: str) -> str:
        """
        Handle an incoming message from a user.

        Args:
            user_id: WhatsApp user ID (format: <number>@s.whatsapp.net)
            message_text: The message content

        Returns:
            Response text to send back to the user
        """
        logger.info(f"[COACH] Processing message from {user_id}")

        # STEP 1: Safety Interceptor (BEFORE LLM)
        safety_check = self.safety.check_message(message_text)

        if safety_check.has_red_flag:
            logger.warning("[SAFETY] RED FLAG DETECTED - Sending emergency response")
            return safety_check.response  # type: ignore

        # STEP 2: Initialize user if needed
        await self._initialize_user(user_id)

        try:
            # STEP 3: Get conversation history
            messages = self._get_conversation_history(user_id)

            # STEP 3.5: Build user context and prepend to message
            user_context = self._build_user_context(user_id)
            message_with_context = message_text
            if user_context:
                message_with_context = f"{user_context}\n\n---\nUser message: {message_text}"

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
            # Create user with default surgery date from settings
            surgery_date = (
                self.settings.surgery_date
                or date.today().isoformat()
            )

            self.db.set_surgery_date(user_id, surgery_date)
            logger.info(
                f"[COACH] Initialized new user: {user_id} "
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

    def _build_user_context(self, user_id: str) -> str | None:
        """
        Build context string with user's surgery date and latest metrics.

        This context is prepended to every user message to give the LLM
        relevant information for providing personalized responses.
        """
        context_parts = []

        # Get user config (surgery date)
        user_config = self.db.get_user_config(user_id)
        if user_config and user_config.surgery_date:
            try:
                surgery = datetime.strptime(user_config.surgery_date, "%Y-%m-%d").date()
                today = date.today()
                days_post_op = (today - surgery).days
                weeks_post_op = days_post_op // 7

                if days_post_op >= 0:
                    # Determine phase
                    if weeks_post_op < 2:
                        phase = "Phase 1 (Protection & Initial Recovery)"
                    elif weeks_post_op < 6:
                        phase = "Phase 2 (Early Strengthening)"
                    elif weeks_post_op < 12:
                        phase = "Phase 3 (Progressive Loading)"
                    else:
                        phase = "Phase 4 (Return to Sport Preparation)"

                    context_parts.append(
                        f"[USER CONTEXT]\n"
                        f"Surgery Date: {user_config.surgery_date}\n"
                        f"Days Post-Op: {days_post_op}\n"
                        f"Weeks Post-Op: {weeks_post_op}\n"
                        f"Current Phase: {phase}"
                    )
                else:
                    # Surgery is in the future
                    context_parts.append(
                        f"[USER CONTEXT]\n"
                        f"Scheduled Surgery Date: {user_config.surgery_date}\n"
                        f"Days Until Surgery: {-days_post_op}"
                    )

                if user_config.surgeon_name:
                    context_parts.append(f"Surgeon: {user_config.surgeon_name}")
                if user_config.surgery_type:
                    context_parts.append(f"Surgery Type: {user_config.surgery_type}")

            except ValueError:
                pass  # Invalid date format, skip

        # Get latest metrics
        latest_metrics = self.db.get_latest_metrics(user_id)
        if latest_metrics:
            context_parts.append(
                f"\n[LATEST CHECK-IN ({latest_metrics.date})]\n"
                f"Pain Level: {latest_metrics.pain_level}/10\n"
                f"Swelling: {latest_metrics.swelling_status}\n"
                f"ROM Extension: {latest_metrics.rom_extension}°\n"
                f"ROM Flexion: {latest_metrics.rom_flexion}°\n"
                f"Exercise Adherence: {'Yes' if latest_metrics.adherence else 'No'}"
            )
            if latest_metrics.notes:
                context_parts.append(f"Notes: {latest_metrics.notes}")

        # Get trends if available
        trends = self.db.get_metrics_trends(user_id, 7)
        if trends:
            trend_str = []
            if trends.pain_trend != 0:
                trend_str.append(f"Pain {'↑' if trends.pain_trend > 0 else '↓'}{abs(trends.pain_trend)}")
            if trends.rom_flexion_trend != 0:
                trend_str.append(f"Flexion {'↑' if trends.rom_flexion_trend > 0 else '↓'}{abs(trends.rom_flexion_trend)}°")
            if trends.adherence_rate < 1.0:
                trend_str.append(f"Adherence: {trends.adherence_rate:.0%}")
            
            if trend_str:
                context_parts.append(f"7-Day Trends: {', '.join(trend_str)}")

        if context_parts:
            return "\n".join(context_parts)
        return None

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
