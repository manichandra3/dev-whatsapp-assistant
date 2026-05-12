"""
Scheduler Module - Handles proactive reminders via APScheduler.
"""

import logging
from datetime import timedelta
from pathlib import Path

import httpx
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: AsyncIOScheduler | None = None
_node_bridge_port: int = 3000


def init_scheduler(db_path: str, bridge_port: int = 3000) -> AsyncIOScheduler:
    """Initialize the APScheduler with a separate SQLAlchemy Job Store."""
    global scheduler, _node_bridge_port
    _node_bridge_port = bridge_port
    if scheduler:
        return scheduler

    app_db_path = Path(db_path)
    scheduler_db_path = app_db_path.with_name(
        f"{app_db_path.stem}_scheduler{app_db_path.suffix}"
    )
    scheduler_db_path.parent.mkdir(parents=True, exist_ok=True)

    jobstores = {"default": SQLAlchemyJobStore(url=f"sqlite:///{scheduler_db_path}")}

    scheduler = AsyncIOScheduler(jobstores=jobstores)
    scheduler.start(paused=True)
    _prune_invalid_interval_jobs(scheduler)
    scheduler.resume()
    logger.info(f"[SCHEDULER] Started APScheduler using job store {scheduler_db_path}")
    return scheduler


def _prune_invalid_interval_jobs(
    active_scheduler: AsyncIOScheduler,
    min_interval_minutes: int = 15,
) -> None:
    """Remove persisted interval jobs that run more frequently than allowed."""
    min_interval = timedelta(minutes=min_interval_minutes)

    for job in active_scheduler.get_jobs():
        interval = getattr(job.trigger, "interval", None)
        if interval is not None and interval < min_interval:
            logger.warning(
                "[SCHEDULER] Removing invalid reminder job %s with interval %s",
                job.id,
                interval,
            )
            active_scheduler.remove_job(job.id)


def get_scheduler() -> AsyncIOScheduler | None:
    """Get the global scheduler instance."""
    return scheduler


async def send_scheduled_reminder(
    user_id: str, message_type: str, content: str
) -> None:
    """Job function to send the reminder via Node.js bridge."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://127.0.0.1:{_node_bridge_port}/api/send-message",
                json={"userId": user_id, "messageText": content},
                timeout=10.0,
            )
            response.raise_for_status()
            logger.info(
                f"[SCHEDULER] Successfully pushed reminder to {user_id}: {content}"
            )
    except Exception as e:
        logger.error(f"[SCHEDULER] Failed to push reminder to {user_id}: {e}")
