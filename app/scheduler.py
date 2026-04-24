"""Background scheduler that dispatches due reminders."""

import asyncio
import logging

import httpx

from app.config import Settings
from app.database import DatabaseManager, ScheduledTask

logger = logging.getLogger(__name__)


class ReminderScheduler:
    """Polls scheduled tasks and delivers reminders via bridge callback."""

    def __init__(self, db: DatabaseManager, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.poll_interval_seconds = max(5, settings.scheduler_poll_interval_seconds)
        self.batch_size = max(1, settings.scheduler_batch_size)
        self.enabled = settings.scheduler_enabled
        self.callback_url = settings.scheduler_delivery_callback_url.rstrip("/")
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start scheduler loop."""
        if not self.enabled:
            logger.info("[SCHEDULER] Disabled by configuration")
            return

        if self._task and not self._task.done():
            return

        logger.info(
            "[SCHEDULER] Starting (poll=%ss, batch=%s, callback=%s)",
            self.poll_interval_seconds,
            self.batch_size,
            self.callback_url,
        )
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="reminder-scheduler")

    async def stop(self) -> None:
        """Stop scheduler loop gracefully."""
        if not self._task:
            return

        logger.info("[SCHEDULER] Stopping")
        self._stop_event.set()
        await self._task
        self._task = None
        logger.info("[SCHEDULER] Stopped")

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                due_tasks = self.db.get_due_scheduled_tasks(limit=self.batch_size)
                for task in due_tasks:
                    await self._deliver(task)
            except Exception as exc:
                logger.error("[SCHEDULER] Poll loop error: %s", exc)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval_seconds)
            except TimeoutError:
                continue

    async def _deliver(self, task: ScheduledTask) -> None:
        reminder_text = f"⏰ Reminder: {task.task_description}"
        payload = {
            "user_id": task.user_id,
            "message_text": reminder_text,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(f"{self.callback_url}/send", json=payload)
                response.raise_for_status()
                body = response.json()

            if body.get("success"):
                self.db.mark_scheduled_task_delivered(task.id)
                logger.info("[SCHEDULER] Delivered task id=%s user=%s", task.id, task.user_id)
            else:
                raise RuntimeError(f"Callback returned failure: {body}")
        except Exception as exc:
            self.db.mark_scheduled_task_pending(task.id)
            logger.error("[SCHEDULER] Delivery failed for task id=%s: %s", task.id, exc)
