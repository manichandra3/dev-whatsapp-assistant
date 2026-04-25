import logging
import subprocess
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import get_settings
from app.database import DatabaseManager
from datetime import datetime

logger = logging.getLogger(__name__)

class ProactiveAgent:
    """Manages proactive tasks like system health checks and morning briefs using APScheduler."""

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.settings = get_settings()
        self.scheduler = AsyncIOScheduler()
        self.callback_url = self.settings.scheduler_delivery_callback_url.rstrip("/")
        # Change this to your primary WhatsApp JID (phone number with @s.whatsapp.net)
        self.admin_jid = "YOUR_NUMBER_HERE@s.whatsapp.net"

    async def start(self):
        """Start the background scheduler and add proactive jobs."""
        logger.info("[PROACTIVE] Starting APScheduler for proactive tasks...")
        
        # System Health Check - Runs every 5 minutes
        self.scheduler.add_job(
            self.task_monitor_health,
            trigger='interval',
            minutes=5,
            id='system_health_check',
            name='System Health Monitor',
            replace_existing=True
        )

        # Morning Brief - Runs daily at 08:00 AM
        self.scheduler.add_job(
            self.morning_brief,
            trigger='cron',
            hour=8,
            minute=0,
            id='morning_brief',
            name='Daily Morning Briefing',
            replace_existing=True
        )

        self.scheduler.start()
        logger.info("[PROACTIVE] APScheduler started.")

    async def stop(self):
        """Stop the background scheduler."""
        logger.info("[PROACTIVE] Stopping APScheduler...")
        self.scheduler.shutdown()

    async def _send_message(self, jid: str, message: str):
        """Send a POST request to the Node.js bridge to deliver a WhatsApp message."""
        payload = {
            "user_id": jid,  # Bridge accepts user_id
            "message_text": message
        }

        # Include HMAC signature if configured
        headers = {}
        if self.settings.scheduler_callback_secret:
            import hmac, hashlib, json
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
                logger.info(f"[PROACTIVE] Sent proactive message to {jid}")
        except Exception as e:
            logger.error(f"[PROACTIVE] Failed to send proactive message: {e}")

    async def task_monitor_health(self):
        """Check system health (disk/cpu) using subprocess and ping if threshold exceeded."""
        logger.info("[PROACTIVE] Running System Health Check...")
        try:
            # Check Disk Space
            disk_result = subprocess.run(
                ["df", "-h", "/"], 
                capture_output=True, 
                text=True, 
                check=True
            )
            
            # Simple parsing of `df -h /` output
            lines = disk_result.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                use_percent = int(parts[4].replace("%", ""))
                
                # Check CPU load (1-minute average) via uptime
                uptime_result = subprocess.run(["uptime"], capture_output=True, text=True)
                # Example: ... load average: 2.15, 1.95, 1.80
                load_avg = uptime_result.stdout.split("load average:")[1].split(",")[0].strip()

                alert_msg = ""
                if use_percent > 85:
                    alert_msg += f"⚠️ *High Disk Usage:* {use_percent}%\n"
                if float(load_avg) > 4.0:  # Assuming 4 cores threshold
                    alert_msg += f"⚠️ *High CPU Load:* {load_avg}\n"

                if alert_msg:
                    message = "🚨 *System Health Alert*\n\n" + alert_msg
                    await self._send_message(self.admin_jid, message)
                    
        except Exception as e:
            logger.error(f"[PROACTIVE] Error in health check: {e}")

    async def morning_brief(self):
        """Pull top 3 items from scheduled_tasks (or a todos table) and message."""
        logger.info("[PROACTIVE] Generating Morning Brief...")
        try:
            # We'll pull pending scheduled tasks as 'todos' for the day
            pending_tasks = self.db.get_user_tasks(self.admin_jid)
            
            if not pending_tasks:
                return

            brief = "🌅 *Good Morning! Here is your brief for today:*\n\n*Top pending tasks:*\n"
            
            for idx, task in enumerate(pending_tasks[:3]):
                due_info = task.due_at if task.due_at else "No due date"
                brief += f"{idx+1}. {task.task_description} (Due: {due_info})\n"

            brief += "\nHave a productive day! 🚀"
            
            await self._send_message(self.admin_jid, brief)
            
        except Exception as e:
            logger.error(f"[PROACTIVE] Error generating morning brief: {e}")
