"""
Scheduler Module - Handles proactive reminders via APScheduler.
"""

import logging
from datetime import timedelta, datetime, timezone
from pathlib import Path
from sqlalchemy import text

import httpx
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: AsyncIOScheduler | None = None
_node_bridge_port: int = 3000
_bridge_health_path: str = "/health"
_bridge_send_path: str = "/api/send-message"


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

    # Ensure we pass an absolute path string to SQLAlchemyJobStore
    jobstores = {"default": SQLAlchemyJobStore(url=f"sqlite:///{scheduler_db_path.absolute()}")}

    scheduler = AsyncIOScheduler(jobstores=jobstores)
    # Start paused to allow pruning/restores safely
    scheduler.start(paused=True)
    _prune_invalid_interval_jobs(scheduler)
    # Resume normal operation
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
    user_id: str, message_type: str, content: str, reminder_id: str | None = None
) -> None:
    """Job function to send the reminder via Node.js bridge."""
    try:
        from app.database import DatabaseManager
        from app.config import get_settings
        db = DatabaseManager()
        settings = get_settings()

        engine = db.get_engine_or_raise()
        with engine.connect() as conn:
            user = conn.execute(text("SELECT * FROM user_config WHERE user_id = :uid"), {"uid": user_id}).fetchone()
            
            # Rate limiting / Safeguards
            if user:
                col_names = [c[0] for c in conn.execute(text("PRAGMA table_info(user_config)")).fetchall()]
                last_msg = None
                opt_in = False
                messages_sent_today = 0
                last_sent_date = None
                
                if 'last_user_message_at' in col_names and user[col_names.index('last_user_message_at')]:
                    last_msg = datetime.fromisoformat(user[col_names.index('last_user_message_at')])
                if 'whatsapp_reminder_opt_in' in col_names:
                    opt_in = bool(user[col_names.index('whatsapp_reminder_opt_in')])
                if 'messages_sent_today' in col_names:
                    messages_sent_today = user[col_names.index('messages_sent_today')]
                if 'last_sent_date' in col_names:
                    last_sent_date = user[col_names.index('last_sent_date')]
                    
                today_str = datetime.now(timezone.utc).date().isoformat()
                
                if last_sent_date != today_str:
                    messages_sent_today = 0
                    
                if messages_sent_today >= settings.max_messages_per_user_per_day:
                    logger.warning(f"[SCHEDULER] User {user_id} hit rate limit, skipping")
                    return
                    
                if settings.require_reminder_opt_in and not opt_in:
                    logger.warning(f"[SCHEDULER] User {user_id} not opted in, skipping")
                    return
                    
                if last_msg:
                    delta = datetime.now(timezone.utc) - last_msg.replace(tzinfo=timezone.utc) if last_msg.tzinfo is None else last_msg
                    if delta > timedelta(hours=24) and not settings.whatsapp_business_api_mode:
                        logger.warning(f"[SCHEDULER] User {user_id} outside 24h window, skipping")
                        return

        async with httpx.AsyncClient() as client:
            try:
                health = await client.get(f"http://127.0.0.1:{_node_bridge_port}{_bridge_health_path}", timeout=2.0)
                if health.status_code != 200 or health.json().get("status") not in ("ok", "healthy"):
                    logger.warning("[SCHEDULER] Bridge unhealthy, skipping")
                    return
            except Exception as e:
                logger.warning(f"[SCHEDULER] Bridge health check failed: {e}")
                return

            payload = {"userId": user_id, "messageText": content, "context": {"reminder_id": str(reminder_id) if reminder_id else None}}
            
            # Interactive payload example if enabled
            if settings.enable_interactive_messages:
                payload["whatsapp_payload"] = {
                    "type": "buttons",
                    "body": {"text": content},
                    "buttons": [{"id": f"ack_{reminder_id}", "text": "Got it ✓"}]
                }
            
            response = await client.post(
                f"http://127.0.0.1:{_node_bridge_port}{_bridge_send_path}",
                json=payload,
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            
            # Update counts
            with engine.connect() as conn:
                today_str = datetime.now(timezone.utc).date().isoformat()
                conn.execute(text("""
                    UPDATE user_config SET 
                    messages_sent_today = CASE WHEN last_sent_date = :today THEN messages_sent_today + 1 ELSE 1 END,
                    last_sent_date = :today
                    WHERE user_id = :uid
                """), {"uid": user_id, "today": today_str})
                conn.commit()

            stanza_id = data.get("stanzaId") or data.get("messageId")
            if stanza_id and reminder_id:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("UPDATE reminders SET last_stanza_id = :sid WHERE job_id = :jid"),
                            {"sid": stanza_id, "jid": f"rem_{reminder_id}"},
                        )
                        conn.commit()
                except Exception as e:
                    logger.warning(f"[SCHEDULER] Failed to persist stanza id: {e}")

            logger.info(f"[SCHEDULER] Successfully pushed reminder to {user_id}")
    except Exception as e:
        logger.exception(f"[SCHEDULER] Failed to push reminder to {user_id}: {e}")

