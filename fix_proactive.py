import re
with open("app/proactive.py", "r") as f:
    content = f.read()

# Fix the method signature: the task variables are not standard strings
new_code = """
                if alert_msg:
                    message = "🚨 *System Health Alert*\\n\\n" + alert_msg
                    await self._send_message(self.admin_jid, message)
                    
        except Exception as e:
            logger.error(f"[PROACTIVE] Error in health check: {e}")

    async def morning_brief(self):
        \"\"\"Pull top 3 items from scheduled_tasks (or a todos table) and message.\"\"\"
        logger.info("[PROACTIVE] Generating Morning Brief...")
        try:
            # We'll pull pending scheduled tasks as 'todos' for the day
            pending_tasks = self.db.get_user_tasks(self.admin_jid)
            
            if not pending_tasks:
                return

            brief = "🌅 *Good Morning! Here is your brief for today:*\\n\\n*Top pending tasks:*\\n"
            
            for idx, task in enumerate(pending_tasks[:3]):
                due_info = task.due_at if task.due_at else "No due date"
                brief += f"{idx+1}. {task.task_description} (Due: {due_info})\\n"

            brief += "\\nHave a productive day! 🚀"
            
            await self._send_message(self.admin_jid, brief)
            
        except Exception as e:
            logger.error(f"[PROACTIVE] Error generating morning brief: {e}")
"""

content = content.replace('                if alert_msg:\n                    message = "🚨 *System Health Alert*\n\n" + alert_msg\n                    await self._send_message(self.admin_jid, message)\n                    \n        except Exception as e:\n            logger.error(f"[PROACTIVE] Error in health check: {e}")\n\n    async def morning_brief(self):\n        """Pull top 3 items from scheduled_tasks (or a todos table) and message."""\n        logger.info("[PROACTIVE] Generating Morning Brief...")\n        try:\n            # We\'ll pull pending scheduled tasks as \'todos\' for the day\n            pending_tasks = self.db.get_user_tasks(self.admin_jid)\n            \n            if not pending_tasks:\n                return\n\n            brief = "🌅 *Good Morning! Here is your brief for today:*\n\n*Top pending tasks:*\n"\n            \n            for idx, task in enumerate(pending_tasks[:3]):\n                due_info = task.due_at if task.due_at else "No due date"\n                brief += f"{idx+1}. {task.task_description} (Due: {due_info})\n"\n\n            brief += "\nHave a productive day! 🚀"\n            \n            await self._send_message(self.admin_jid, brief)\n            \n        except Exception as e:\n            logger.error(f"[PROACTIVE] Error generating morning brief: {e}")', new_code)
with open("app/proactive.py", "w") as f:
    f.write(content)
