"""
Delivery Dispatcher for the WhatsApp Assistant.

Translates intent classifications into user-facing actions and text.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from app.database import DatabaseManager
from app.llm.providers import LLMProvider

logger = logging.getLogger(__name__)


class DeliveryService:
    """Orchestrates fulfilling the user's intent after classification."""

    def __init__(self, db: DatabaseManager, llm: LLMProvider):
        self.db = db
        self.llm = llm

    async def deliver(self, intent: str, topic: str, metadata: dict[str, Any], user_id: str, message_text: str) -> str:
        """
        Execute actions for a classified intent and return a human-readable reply.
        """
        logger.info(f"[DELIVERY] Fulfilling intent: {intent} for user: {user_id}")
        
        try:
            if intent == "schedule_task":
                return await self._handle_schedule_task(user_id, topic, metadata)
            elif intent == "log_expense":
                return await self._handle_log_expense(user_id, topic, metadata, message_text)
            elif intent == "execute_code":
                return await self._handle_execute_code(user_id, topic, metadata)
            elif intent == "debug_code":
                return await self._handle_debug_code(user_id, topic, metadata)
            elif intent == "summarize_link":
                return await self._handle_summarize_link(user_id, topic, metadata)
            elif intent == "general_chat":
                return await self._handle_general_chat(user_id, message_text)
            else:
                return f"I understood you wanted to '{intent}', but I haven't learned how to do that yet."
                
        except Exception as e:
            logger.error(f"[DELIVERY] Error fulfilling intent {intent}: {e}")
            return "I encountered an issue trying to complete that request. Please try again later."

    async def _handle_schedule_task(self, user_id: str, topic: str, metadata: dict[str, Any]) -> str:
        desc = metadata.get("task", topic)
        time_value = metadata.get("time")
        freq = metadata.get("frequency")

        if not time_value:
            return f"I can help schedule '{desc}'. What time would you like to be reminded?"

        due_at = self._parse_due_time(str(time_value))
        if not due_at:
            return (
                f"I can schedule '{desc}', but I need an exact date/time. "
                "Please use a clear format like '2026-04-25 18:30' or ISO '2026-04-25T18:30:00+05:30'."
            )

        freq_str = freq if freq else "once"
        details = f"Time: {time_value}, Frequency: {freq_str}"

        self.db.save_scheduled_task(user_id, desc, details, due_at, freq_str)
        return f"✅ Got it. I'll remind you to '{desc}' ({details})."

    def _parse_due_time(self, raw_time: str) -> datetime | None:
        """Parse scheduled time from common formats into timezone-aware UTC datetime."""
        parsed: datetime | None = None
        value = raw_time.strip()
        if not value:
            return None

        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            parsed = None

        if parsed is None:
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
                try:
                    parsed = datetime.strptime(value, fmt)
                    break
                except ValueError:
                    continue

        if parsed is None:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)

        return parsed.astimezone(UTC)

    async def _handle_log_expense(self, user_id: str, topic: str, metadata: dict[str, Any], message_text: str) -> str:
        amount = str(metadata.get("amount", "Unknown"))
        currency = str(metadata.get("currency", "USD"))
        category = str(metadata.get("category", topic))
        note = str(metadata.get("note", ""))
        
        self.db.log_expense(user_id, amount, currency, category, note, message_text)
        return f"💸 Logged expense: {amount} {currency} for {category}."

    async def _handle_execute_code(self, user_id: str, topic: str, metadata: dict[str, Any]) -> str:
        code = metadata.get("code", "")
        language = metadata.get("language", "python").lower()
        
        if language != "python":
            return f"I currently only support executing Python code, but you asked for {language}."
            
        if not code:
            return "I couldn't find the code snippet to execute."
            
        # Basic MVP static analysis / blocklist
        blocked_patterns = ["os.system", "subprocess", "eval", "exec", "open(", "import os", "import subprocess", "import pty"]
        for pattern in blocked_patterns:
            if pattern in code:
                return f"⚠️ Execution blocked: the code contains unsafe patterns (`{pattern}`)."
            
        import tempfile
        import subprocess
        import os
        
        output_str = ""
        exit_code = -1
        runtime = 0
        
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                temp_path = f.name
                
            try:
                # Python-only sandbox MVP limits
                import time
                start_time = time.time()
                result = subprocess.run(["python3", temp_path], capture_output=True, text=True, timeout=5) # Reduced timeout to 5
                runtime = int((time.time() - start_time) * 1000)
                exit_code = result.returncode
                
                stdout = result.stdout[:2000] if result.stdout else ""
                stderr = result.stderr[:2000] if result.stderr else ""
                
                if exit_code == 0:
                    output_str = f"✅ Execution successful ({runtime}ms):\n\n"
                    if stdout:
                        output_str += f"```text\n{stdout}\n```"
                    else:
                        output_str += "*(No output)*"
                else:
                    output_str = f"❌ Execution failed (exit code {exit_code}):\n\n"
                    if stderr:
                        output_str += f"```text\n{stderr}\n```"
                    elif stdout:
                        output_str += f"```text\n{stdout}\n```"
                        
                log_out = (stdout + stderr)[:1000]
                self.db.log_code_run(user_id, "python", code, exit_code, runtime, log_out)
                
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                    
        except subprocess.TimeoutExpired:
            output_str = "⏳ Execution timed out after 5 seconds."
            self.db.log_code_run(user_id, "python", code, 124, 5000, "Timeout")
        except Exception as e:
            output_str = f"⚠️ System error during execution: {e}"
            
        return output_str

    async def _handle_debug_code(self, user_id: str, topic: str, metadata: dict[str, Any]) -> str:
        error = metadata.get("error", "")
        code = metadata.get("code", "")
        
        prompt = f"Please act as an expert developer and debug this.\n\nError: {error}\n\nCode context: {code}"
        
        messages = [
            {"role": "system", "content": "You are a helpful coding assistant. Provide a very concise explanation of the bug and a short fix."},
            {"role": "user", "content": prompt}
        ]
        
        response = await self.llm.chat(messages)
        return f"🔍 Debugging Analysis:\n\n{response.content}"

    async def _handle_summarize_link(self, user_id: str, topic: str, metadata: dict[str, Any]) -> str:
        url = metadata.get("url", "")
        text_content = metadata.get("text", "")
        
        content_to_summarize = text_content
        
        if url and not text_content:
            if not (url.startswith("http://") or url.startswith("https://")):
                return f"I can only summarize valid HTTP/HTTPS URLs, but received: {url}"
            try:
                import urllib.request
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as response:
                    content_type = response.headers.get('Content-Type', '').lower()
                    if 'text/html' not in content_type and 'text/plain' not in content_type:
                        return f"I can only summarize text-based webpages, but the link points to a non-text type: {content_type}"
                    
                    content_to_summarize = response.read().decode('utf-8')[:10000] # Cap length to 10000
            except Exception as e:
                return f"I couldn't fetch the link: {e}"
                
        if not content_to_summarize:
            return "I couldn't find any content to summarize."
            
        messages = [
            {"role": "system", "content": "You are a helpful assistant. Provide a brief, bulleted summary of the following content."},
            {"role": "user", "content": content_to_summarize}
        ]
        
        response = await self.llm.chat(messages)
        return f"📝 Summary:\n\n{response.content}"

    async def _handle_general_chat(self, user_id: str, message_text: str) -> str:
        recent_messages = self.db.get_recent_messages(user_id, limit=6)
        
        messages = [
            {"role": "system", "content": "You are a helpful developer assistant reachable on WhatsApp. Keep your answers concise, practical, and formatted well using markdown."}
        ]
        messages.extend(recent_messages)
        # Add the current message if it's not already the last one
        if not messages or messages[-1].get("content") != message_text:
            messages.append({"role": "user", "content": message_text})
            
        response = await self.llm.chat(messages)
        return str(response.content)
