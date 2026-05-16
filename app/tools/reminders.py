import logging
import uuid
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import text

from app.database import DatabaseManager
from app.scheduler import get_scheduler, send_scheduled_reminder

logger = logging.getLogger(__name__)


def set_reminder(
    db: DatabaseManager,
    user_id: str,
    task: str,
    schedule_type: str,
    time_value: str,
) -> dict[str, Any]:
    scheduler = get_scheduler()
    if not scheduler:
        return {"error": True, "message": "Scheduler not initialized"}

    reminder_id = str(uuid.uuid4())
    job_id = f"rem_{reminder_id}"
    content = f"Reminder: {task}. Reply 'Done' when you've finished."

    try:
        if schedule_type == "daily":
            hours, minutes = map(int, time_value.split(":"))
            trigger = CronTrigger(hour=hours, minute=minutes)
        elif schedule_type == "interval":
            interval_hours = float(time_value)
            if interval_hours < 0.25:
                return {
                    "error": True,
                    "message": "Interval too short. Minimum interval is 0.25 hours (15 minutes).",
                }
            trigger = IntervalTrigger(seconds=int(interval_hours * 3600))
        else:
            return {
                "error": True,
                "message": f"Unknown schedule_type: {schedule_type}",
            }

        scheduler.add_job(
            send_scheduled_reminder,
            trigger=trigger,
            args=[user_id, "reminder", content, reminder_id],
            id=job_id,
            replace_existing=True,
        )

        try:
            engine = db.engine
            if engine is None:
                raise RuntimeError("Database engine is not initialized")
            with engine.connect() as conn:
                conn.execute(
                    text(
                        "INSERT INTO reminders (user_id, job_id, reminder_type, interval_expression, is_active) "
                        "VALUES (:uid, :jid, :type, :expr, :active)"
                    ),
                    {
                        "uid": user_id,
                        "jid": job_id,
                        "type": task,
                        "expr": f"{schedule_type}_{time_value}",
                        "active": 1,
                    },
                )
                conn.commit()
        except Exception as e:
            logger.warning(
                "[TOOL] Reminder job %s was scheduled, but metadata persistence failed: %s",
                job_id,
                e,
            )

        return {
            "success": True,
            "message": f"Reminder for '{task}' set successfully with ID {reminder_id}.",
            "reminder_id": reminder_id
        }
    except Exception as e:
        return {"error": True, "message": str(e)}


def list_reminders(db: DatabaseManager, user_id: str) -> dict[str, Any]:
    engine = db.engine
    if engine is None:
        return {"error": True, "message": "Database not initialized"}

    scheduler = get_scheduler()

    try:
        with engine.connect() as conn:
            results = conn.execute(
                text("SELECT id, job_id, reminder_type, interval_expression, is_active FROM reminders WHERE user_id = :uid AND is_active = 1"),
                {"uid": user_id}
            ).fetchall()

        reminders = []
        for row in results:
            job_id = row.job_id
            r_id = job_id.replace("rem_", "") if job_id else str(row.id)
            friendly = "Unknown schedule"
            next_run = "No job"

            try:
                if scheduler and job_id:
                    job = scheduler.get_job(str(job_id))
                    if job is None:
                        friendly = "Scheduled (job missing)"
                    else:
                        nrt = job.next_run_time
                        if nrt is None:
                            next_run = "Paused"
                        else:
                            try:
                                next_run = nrt.isoformat()
                            except Exception:
                                next_run = str(nrt)

                        trig_name = job.trigger.__class__.__name__
                        if trig_name == "CronTrigger":
                            friendly = f"Cron: {str(job.trigger)}"
                        elif trig_name == "IntervalTrigger":
                            friendly = f"Interval: {str(job.trigger)}"
                        else:
                            friendly = f"{trig_name}: {str(job.trigger)}"

            except Exception:
                friendly = row.interval_expression or "Custom"

            reminders.append({
                "id": r_id,
                "task": row.reminder_type,
                "schedule": friendly,
                "next_run": next_run,
                "active": bool(row.is_active),
            })

        return {
            "success": True,
            "reminders": reminders,
            "message": f"Found {len(reminders)} active reminders."
        }
    except Exception as e:
        logger.exception("[TOOL] Error listing reminders: %s", e)
        return {"error": True, "message": str(e)}


def delete_reminder(db: DatabaseManager, user_id: str, reminder_id: str) -> dict[str, Any]:
    scheduler = get_scheduler()
    job_id = f"rem_{reminder_id}"

    if scheduler and scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    engine = db.engine
    try:
        with engine.connect() as conn:
            conn.execute(
                text("DELETE FROM reminders WHERE user_id = :uid AND job_id = :jid"),
                {"uid": user_id, "jid": job_id}
            )
            conn.commit()
        return {"success": True, "message": f"Reminder {reminder_id} deleted."}
    except Exception as e:
        return {"error": True, "message": str(e)}


def pause_reminder(db: DatabaseManager, user_id: str, reminder_id: str) -> dict[str, Any]:
    scheduler = get_scheduler()
    job_id = f"rem_{reminder_id}"

    if scheduler and scheduler.get_job(job_id):
        scheduler.pause_job(job_id)

    engine = db.engine
    try:
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE reminders SET is_active = 0 WHERE user_id = :uid AND job_id = :jid"),
                {"uid": user_id, "jid": job_id}
            )
            conn.commit()
        return {"success": True, "message": f"Reminder {reminder_id} paused."}
    except Exception as e:
        return {"error": True, "message": str(e)}


def resume_reminder(db: DatabaseManager, user_id: str, reminder_id: str) -> dict[str, Any]:
    scheduler = get_scheduler()
    job_id = f"rem_{reminder_id}"

    if scheduler and scheduler.get_job(job_id):
        scheduler.resume_job(job_id)

    engine = db.engine
    try:
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE reminders SET is_active = 1 WHERE user_id = :uid AND job_id = :jid"),
                {"uid": user_id, "jid": job_id}
            )
            conn.commit()
        return {"success": True, "message": f"Reminder {reminder_id} resumed."}
    except Exception as e:
        return {"error": True, "message": str(e)}


def update_reminder(db: DatabaseManager, user_id: str, reminder_id: str, schedule_type: str, time_value: str) -> dict[str, Any]:
    scheduler = get_scheduler()
    job_id = f"rem_{reminder_id}"

    engine = db.engine
    task = "task"
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT reminder_type FROM reminders WHERE user_id = :uid AND job_id = :jid"),
                {"uid": user_id, "jid": job_id}
            ).fetchone()
            if result:
                task = result.reminder_type
            else:
                return {"error": True, "message": f"Reminder {reminder_id} not found in database."}

            if schedule_type == "daily":
                hours, minutes = map(int, time_value.split(":"))
                trigger = CronTrigger(hour=hours, minute=minutes)
            elif schedule_type == "interval":
                interval_hours = float(time_value)
                trigger = IntervalTrigger(seconds=int(interval_hours * 3600))
            else:
                return {"error": True, "message": f"Unknown schedule_type: {schedule_type}"}

            if scheduler:
                content = f"Reminder: {task}. Reply 'Done' when you've finished."
                scheduler.modify_job(job_id, args=[user_id, "reminder", content])
                scheduler.reschedule_job(job_id, trigger=trigger)

            conn.execute(
                text("UPDATE reminders SET interval_expression = :expr WHERE user_id = :uid AND job_id = :jid"),
                {"expr": f"{schedule_type}_{time_value}", "uid": user_id, "jid": job_id}
            )
            conn.commit()
        return {"success": True, "message": f"Reminder {reminder_id} updated successfully."}
    except Exception as e:
        return {"error": True, "message": str(e)}


def log_adherence(db: DatabaseManager, user_id: str, task: str, status: str) -> dict[str, Any]:
    success = db.log_adherence(
        user_id=user_id, reminder_type=task, status=status
    )
    if success:
        return {
            "success": True,
            "message": f"Successfully logged {status} for {task}.",
        }
    return {"error": True, "message": "Failed to log adherence in database."}
