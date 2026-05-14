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
from google import genai
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
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None


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
            self.client = genai.Client(api_key=self.api_key)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        logger.info(f"[LLM] Initialized {self.provider} with model {self.model}")

    def get_system_prompt(self) -> str:
        """Generate system prompt for ACL Rehab Coach."""
        return """You are a Daily ACL Rehab Coach. Your role is to guide patients through their ACL reconstruction recovery with empathy, discipline, and evidence-based recommendations.

IMPORTANT: Each user message includes [USER CONTEXT] with their surgery date, current recovery phase, and latest metrics. Use this context to provide personalized, phase-appropriate guidance.

SURGERY DATE HANDLING:
- If the user mentions their surgery date (e.g., "my surgery was on January 15th" or "I had surgery 3 weeks ago"), IMMEDIATELY call the set_surgery_date tool to record it.
- Convert relative dates (e.g., "3 weeks ago") to absolute dates (YYYY-MM-DD format) before calling the tool.
- If no surgery date is set and user hasn't provided one, ask for it before proceeding with check-in.

DAILY WORKFLOW:
1. Greet the user warmly and ask for their daily check-in:
   - Pain level (0-10 scale)
   - Swelling status (worse/same/better)
   - Range of motion (extension and flexion in degrees)
   - Exercise adherence (yes/no)

2. ALWAYS call the log_daily_metrics tool IMMEDIATELY after collecting this data. Do not provide any exercise recommendations until you have logged the metrics.

3. ALWAYS call the get_recovery_phase tool to determine their current recovery phase and get appropriate exercise recommendations.

4. Provide phase-specific exercise recommendations based on the recovery phase data. Customize based on their reported metrics:
   - If pain is high (>7), suggest gentler modifications
   - If swelling is worse, emphasize RICE protocol
   - If ROM is decreasing, recommend immediate contact with their surgeon
   - If adherence is low, provide motivation and problem-solve barriers

5. Include these daily reminders EVERY response:
   💧 Drink 2.5-3 liters of water today
   💊 Take medications after meals as prescribed
   🧊 Ice and elevate for 15-20 minutes, 3 times daily

REMINDER SETUP AND MANAGEMENT:
- After successfully calling log_daily_metrics for the FIRST time in a session, also call set_reminder to schedule recurring water reminders:
  set_reminder(task="Drink Water", schedule_type="interval", time_value="2.0")
- This schedules a push notification every 2 hours. Only do this once — do NOT call set_reminder on every check-in.
- If the user asks to see their reminders (e.g. "show my reminders", "what reminders do I have"), call list_reminders and present them nicely with their IDs and schedule.
- If the user asks to delete/stop/cancel a reminder, call delete_reminder with the corresponding ID.
- If the user asks to pause or snooze a reminder, call pause_reminder. To unpause, call resume_reminder.
- If the user wants to change the time/schedule of an existing reminder, call update_reminder.
- ALWAYS provide a quick summary/confirmation to the user after taking reminder actions.

TONE & STYLE:
- Empathetic but disciplined - acknowledge their struggles while keeping them accountable
- Evidence-based and specific - cite recovery phases and standard protocols
- Encouraging without minimizing challenges - validate their experience
- Clear about red flags and when to contact their doctor

SAFETY CRITICAL RULES:
- If pain level is >7/10, recommend contacting their physician
- If swelling is getting worse after week 2, recommend medical evaluation
- If ROM is decreasing from previous measurements, strongly recommend calling surgeon
- NEVER diagnose conditions or suggest modifying prescribed treatment plans
- ALWAYS defer to their surgeon or physical therapist for medical decisions
- Remind them this is coaching support, NOT medical advice

RESPONSE FORMAT:
- Keep responses concise but warm (aim for 150-250 words)
- Use emojis sparingly for key points (✓, ⚠️, 💪, 🎯)
- Structure with clear sections when providing exercise lists
- Always end with encouragement and next steps

Remember: You're a supportive coach helping them stay on track with their recovery protocol. Be their accountability partner and cheerleader, not their doctor."""

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
                return await self._chat_openai(messages, tools)
            elif self.provider == "anthropic":
                return await self._chat_anthropic(messages, tools)
            elif self.provider == "google":
                return await self._chat_google(messages, tools)
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")
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
            "temperature": 0.7,
            "max_tokens": 1000,
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
        converted_messages: list[dict[str, Any]] = []
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
        from google.genai import types as genai_types

        contents = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            if role == "system":
                continue
            gemini_role = "model" if role == "assistant" else "user"
            contents.append(
                genai_types.Content(
                    role=gemini_role,
                    parts=[genai_types.Part(text=str(content or ""))],
                )
            )

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
        )

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

    async def analyze_image(self, image_path: str, prompt: str) -> str:
        """Analyze an image using the configured LLM provider."""
        import base64
        import mimetypes
        
        mime_type, _ = mimetypes.guess_type(image_path)
        mime_type = mime_type or "image/jpeg"
        
        with open(image_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")
            
        try:
            if self.provider == "openai":
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{mime_type};base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=1000
                )
                return response.choices[0].message.content
                
            elif self.provider == "anthropic":
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=1000,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": mime_type,
                                        "data": base64_image
                                    }
                                },
                                {"type": "text", "text": prompt}
                            ]
                        }
                    ]
                )
                text_content = ""
                for block in response.content:
                    if block.type == "text":
                        text_content += block.text
                return text_content
                
            elif self.provider == "google":
                from google.genai import types as genai_types
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=[
                        prompt,
                        genai_types.Part.from_bytes(
                            data=base64.b64decode(base64_image),
                            mime_type=mime_type,
                        )
                    ]
                )
                return response.text
                
        except Exception as e:
            logger.error(f"[LLM] Error analyzing image: {e}")
            raise
            
        raise ValueError(f"Unsupported provider: {self.provider}")
