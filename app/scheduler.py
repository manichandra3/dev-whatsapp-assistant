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
        
        headers = {}
        if self.settings.scheduler_callback_secret:
            import hmac
            import hashlib
            import json
            payload_bytes = json.dumps(payload).encode("utf-8")
            signature = hmac.new(
                self.settings.scheduler_callback_secret.encode("utf-8"),
                payload_bytes,
                hashlib.sha256,
            ).hexdigest()
            headers["x-hub-signature-256"] = f"sha256={signature}"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{self.callback_url}/send", 
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                body = response.json()

            if body.get("success"):
                # Check if already delivered (idempotency)
                if self.db.is_task_already_delivered(task.id):
                    logger.info("[SCHEDULER] Task id=%s already delivered, skipping", task.id)
                    return
                
                self.db.mark_scheduled_task_delivered(task.id)
                logger.info("[SCHEDULER] Delivered task id=%s user=%s", task.id, task.user_id)
                
                # Handle recurrence: re-schedule if frequency is not 'once'
                if task.frequency and task.frequency != "once" and task.due_at:
                    await self._reschedule_recurring_task(task)
            else:
                raise RuntimeError(f"Callback returned failure: {body}")
        except Exception as exc:
            # Increment attempt count and check max attempts
            self.db.increment_task_attempt(task.id)
            attempts = self.db.get_task_attempt_count(task.id)
            max_attempts = 3
            
            if attempts >= max_attempts:
                self.db.mark_scheduled_task_failed(task.id)
                logger.error("[SCHEDULER] Task id=%s failed after %d attempts, marked as failed", task.id, attempts)
            else:
                # Exponential backoff: delay = 2^attempts minutes (capped at 60 min)
                import math
                delay_minutes = min(2 ** attempts, 60)
                self.db.requeue_scheduled_task_with_delay(task.id, delay_minutes)
                logger.error("[SCHEDULER] Delivery failed for task id=%s (attempt %d/%d), retry in %d min: %s", 
                           task.id, attempts, max_attempts, delay_minutes, exc)

    async def _reschedule_recurring_task(self, task: ScheduledTask) -> None:
        """Re-schedule a recurring task based on its frequency."""
        from datetime import datetime, timezone, timedelta
        
        try:
            # Parse the stored due_at string back to datetime
            if isinstance(task.due_at, str):
                last_due = datetime.fromisoformat(task.due_at.replace('Z', '+00:00'))
            else:
                last_due = task.due_at
            
            if last_due.tzinfo is None:
                last_due = last_due.replace(tzinfo=timezone.utc)
            
            # Calculate next due date based on frequency
            if task.frequency == "daily":
                next_due = last_due + timedelta(days=1)
            elif task.frequency == "weekly":
                next_due = last_due + timedelta(weeks=1)
            elif task.frequency == "monthly":
                next_due = last_due + timedelta(days=30)
            else:
                logger.info("[SCHEDULER] Unknown frequency '%s' for task %s, not rescheduling", task.frequency, task.id)
                return
            
            # Re-insert as new pending task
            self.db.save_scheduled_task(
                user_id=task.user_id,
                description=task.task_description,
                schedule_details=task.schedule_details,
                due_at=next_due,
                frequency=task.frequency
            )
            logger.info("[SCHEDULER] Re-scheduled recurring task id=%s, next due=%s", task.id, next_due)
        except Exception as e:
            logger.error("[SCHEDULER] Failed to re-schedule recurring task id=%s: %s", task.id, e)
