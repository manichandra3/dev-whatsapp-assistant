"""
LLM Provider - Unified interface for OpenAI, Anthropic, and Google Gemini

This module provides a unified interface for interacting with different LLM providers.
It handles message format conversion, tool calling, and provider-specific behaviors.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

import anthropic
import google.generativeai as genai
import openai

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """Represents a tool call from the LLM."""

    id: str
    function_name: str
    arguments: str  # JSON string

    def to_dict(self) -> dict[str, Any]:
        """Convert to OpenAI-compatible format."""
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.function_name,
                "arguments": self.arguments,
            },
        }


@dataclass
class LLMResponse:
    """Response from an LLM call."""

    content: str | None
    finish_reason: str | None = None
    parsed_json: dict[str, Any] | None = None


class LLMProvider:
    """
    Unified LLM provider interface.

    Supports OpenAI, Anthropic, and Google Gemini with consistent message formats.
    """

    def __init__(
        self,
        provider: Literal["openai", "anthropic", "google"],
        model: str,
        api_key: str,
    ) -> None:
        self.provider = provider.lower()
        self.model = model
        self.api_key = api_key
        self.client: Any = None

        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize the appropriate client based on provider."""
        if self.provider == "openai":
            self.client = openai.OpenAI(api_key=self.api_key)
        elif self.provider == "anthropic":
            self.client = anthropic.Anthropic(api_key=self.api_key)
        elif self.provider == "google":
            genai.configure(api_key=self.api_key)
            self.client = genai.GenerativeModel(self.model)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        logger.info(f"[LLM] Initialized {self.provider} with model {self.model}")

    def get_system_prompt(self) -> str:
        """Generate system prompt for Developer WhatsApp Assistant."""
        return """You are the brain of a developer's WhatsApp assistant. Your job is to analyze the user's message, considering the recent conversation history, and determine what action they want to take.
You MUST respond ONLY with a valid, minified JSON object containing the following keys: intent, topic, and metadata.

The intent must be exactly one of the following:
- schedule_task: If the user wants to set a reminder or get daily updates.
- execute_code: If the user provides code and wants to run or test it.
- debug_code: If the user provides an error message, stack trace, or asks about debugging specific lines/files.
- summarize_link: If the user provides a URL or long text to read.
- log_expense: If the user mentions spending money or a cost.
- general_chat: If it is a normal conversation or question.

Example Input: 'Remind me to check the server logs tomorrow morning'
Example Output: {"intent":"schedule_task","topic":"check server logs","metadata":{"frequency":"once","time":"09:00"}}

CRITICAL RULES:
1. DO NOT include historical context in the metadata payload. The topic should be the immediate subject (e.g. "line 42 evaluation").
2. DO NOT output any markdown blocks (like ```json), just the raw minified JSON.
3. ALWAYS ensure the output is parseable by JSON.loads()."""

    def _extract_json(self, text: str | None) -> dict[str, Any] | None:
        """Extract JSON from standard text, or fallback regex search."""
        if not text:
            return None
        import re
        text = text.strip()
        # Remove potential markdown formatting
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Fallback regex search
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
        return None

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """
        Send message to LLM with tools.

        Args:
            messages: Conversation history in OpenAI format
            tools: Optional list of tool definitions

        Returns:
            LLMResponse with content and optional tool calls
        """
        try:
            if self.provider == "openai":
                response = await self._chat_openai(messages, tools)
            elif self.provider == "anthropic":
                response = await self._chat_anthropic(messages, tools)
            elif self.provider == "google":
                response = await self._chat_google(messages, tools)
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")
            
            response.parsed_json = self._extract_json(response.content)
            return response
        except Exception as e:
            logger.error(f"[LLM] Error: {e}")
            raise

    async def _chat_openai(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> LLMResponse:
        """Chat with OpenAI."""
        params: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 1000,
            "response_format": {"type": "json_object"},
        }

        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**params)
        choice = response.choices[0]

        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        function_name=tc.function.name,
                        arguments=tc.function.arguments,
                    )
                )

        return LLMResponse(
            content=choice.message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
        )

    async def _chat_anthropic(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> LLMResponse:
        """Chat with Anthropic Claude."""
        # Extract system message
        system_message = next(
            (m for m in messages if m.get("role") == "system"), None
        )
        conversation_messages = [m for m in messages if m.get("role") != "system"]

        # Convert messages to Anthropic format - normalize ALL content to block arrays
        converted_messages = []
        for msg in conversation_messages:
            role = msg.get("role")
            content = msg.get("content")

            # Skip tool messages - handled differently
            if role == "tool":
                continue

            # If assistant message has OpenAI-style tool_calls, convert to Anthropic blocks
            if role == "assistant" and "tool_calls" in msg:
                content_blocks = []

                # Add text content if exists
                if isinstance(content, str) and content.strip():
                    content_blocks.append({"type": "text", "text": content})
                elif isinstance(content, list):
                    content_blocks.extend(content)

                # Add tool_use blocks
                for tool_call in msg.get("tool_calls", []):
                    if isinstance(tool_call, ToolCall):
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tool_call.id,
                            "name": tool_call.function_name,
                            "input": json.loads(tool_call.arguments),
                        })
                    else:
                        # Handle dict format
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tool_call.get("id"),
                            "name": tool_call.get("function", {}).get("name"),
                            "input": json.loads(
                                tool_call.get("function", {}).get("arguments", "{}")
                            ),
                        })

                converted_messages.append({
                    "role": "assistant",
                    "content": content_blocks,
                })
            # If already content blocks (e.g., tool_result), keep as-is
            elif isinstance(content, list):
                converted_messages.append({"role": role, "content": content})
            # Normalize plain string content into Anthropic text block list
            else:
                converted_messages.append({
                    "role": role,
                    "content": [{"type": "text", "text": str(content or "")}],
                })

        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 1000,
            "messages": converted_messages,
            "system": system_message.get("content") if system_message else self.get_system_prompt(),
        }

        if tools:
            params["tools"] = [
                {
                    "name": t["function"]["name"],
                    "description": t["function"]["description"],
                    "input_schema": t["function"]["parameters"],
                }
                for t in tools
            ]

        response = self.client.messages.create(**params)

        # Parse tool calls from content
        tool_calls = []
        text_content = ""

        for block in response.content:
            if block.type == "text":
                text_content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        function_name=block.name,
                        arguments=json.dumps(block.input),
                    )
                )

        return LLMResponse(
            content=text_content or None,
            tool_calls=tool_calls,
            finish_reason=response.stop_reason,
        )

    async def _chat_google(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> LLMResponse:
        """Chat with Google Gemini."""
        # Convert messages to Gemini format
        history = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            if role == "system":
                # System messages handled separately in Gemini
                continue
            elif role == "assistant":
                history.append({
                    "role": "model",
                    "parts": [{"text": str(content or "")}],
                })
            else:
                history.append({
                    "role": "user",
                    "parts": [{"text": str(content or "")}],
                })

        chat = self.client.start_chat(history=history[:-1] if history else [])

        last_message = history[-1] if history else {"parts": [{"text": ""}]}
        response = chat.send_message(last_message["parts"][0]["text"])

        return LLMResponse(
            content=response.text,
            tool_calls=[],  # Note: Function calling support varies by Gemini model
            finish_reason="stop",
        )

    def format_tool_results_for_anthropic(
        self, tool_results: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Format tool results for Anthropic's expected message format."""
        tool_result_blocks = [
            {
                "type": "tool_result",
                "tool_use_id": tr["tool_call_id"],
                "content": json.dumps(tr["result"]),
            }
            for tr in tool_results
        ]
        return {"role": "user", "content": tool_result_blocks}

    def format_tool_results_for_openai(
        self, tool_results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Format tool results for OpenAI's expected message format."""
        return [
            {
                "role": "tool",
                "tool_call_id": tr["tool_call_id"],
                "name": tr["tool_name"],
                "content": json.dumps(tr["result"]),
            }
            for tr in tool_results
        ]
