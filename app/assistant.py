"""
Developer Assistant Brain - Main Conversation Orchestrator

Coordinates SQLite stateful memory and LLM intent routing.
"""

import json
import logging
from typing import Any

from app.config import Settings
from app.database import DatabaseManager
from app.llm.providers import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class DevAssistantBrain:
    """
    Main orchestrator for the Developer WhatsApp Assistant.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        # Initialize components
        self.db = DatabaseManager(settings.database_path)
        self.llm = LLMProvider(
            provider=settings.llm_provider,
            model=settings.llm_model,
            api_key=settings.get_llm_api_key(),
        )

        logger.info(f"[ASSISTANT] Initialized with provider: {settings.llm_provider}")

    async def handle_message(self, user_id: str, message_text: str) -> str:
        """
        Handle an incoming message from a user.
        """
        logger.info(f"[ASSISTANT] Processing message from {user_id}")

        # Initialize user
        self.db.get_or_create_user(user_id)

        try:
            # 1. Save user message
            self.db.save_message(user_id, "user", message_text)

            # 2. Fetch context
            recent_messages = self.db.get_recent_messages(user_id, limit=10)
            
            # Build messages for LLM
            messages = [{"role": "system", "content": self.llm.get_system_prompt()}]
            messages.extend(recent_messages)

            # 3. Call LLM
            response = await self.llm.chat(messages)

            # 4. Parse output (with Silent Catch)
            if not response.parsed_json or not self._is_valid_intent(response.parsed_json):
                logger.warning(f"[ASSISTANT] Failed to parse valid JSON. Raw output: {response.content}")
                parsed_json = {
                    "intent": "general_chat",
                    "topic": "system_fallback",
                    "metadata": {
                        "response_text": "I had a bit of trouble parsing that request. Could you rephrase it?"
                    }
                }
            else:
                parsed_json = response.parsed_json

            # 5. Save assistant JSON response to SQLite
            json_str = json.dumps(parsed_json, separators=(',', ':'))
            self.db.save_message(user_id, "assistant", json_str)

            # 6. Log parsed intent
            self.db.log_intent(
                user_id=user_id,
                original_message=message_text,
                intent=parsed_json.get("intent", "general_chat"),
                topic=parsed_json.get("topic", "unknown"),
                metadata=parsed_json.get("metadata", {})
            )

            # 7. Return minified JSON string
            return json_str

        except Exception as e:
            logger.error(f"[ASSISTANT] Error processing message: {e}")

            # Fallback JSON on unhandled exception
            fallback = {
                "intent": "general_chat",
                "topic": "system_error",
                "metadata": {
                    "response_text": "I encountered an internal error. Please try again."
                }
            }
            return json.dumps(fallback, separators=(',', ':'))

    def _is_valid_intent(self, data: dict[str, Any]) -> bool:
        """Validate the JSON object has the required keys and valid intent."""
        required_keys = {"intent", "topic", "metadata"}
        if not required_keys.issubset(data.keys()):
            return False
            
        valid_intents = {
            "schedule_task", "execute_code", "debug_code", 
            "summarize_link", "log_expense", "general_chat"
        }
        if data.get("intent") not in valid_intents:
            return False
            
        return True

    def close(self) -> None:
        """Clean up resources."""
        self.db.close()
        logger.info("[ASSISTANT] Shutdown complete")
