import re

with open("app/tools.py", "r") as f:
    content = f.read()

new_tools = """
            {
                "type": "function",
                "function": {
                    "name": "list_reminders",
                    "description": "Lists all active reminders for the user. Call this to show the user their current reminders.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_reminder",
                    "description": "Deletes a specific reminder by its ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reminder_id": {
                                "type": "string",
                                "description": "The unique ID of the reminder to delete."
                            }
                        },
                        "required": ["reminder_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "pause_reminder",
                    "description": "Pauses a specific active reminder by its ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reminder_id": {
                                "type": "string",
                                "description": "The unique ID of the reminder to pause."
                            }
                        },
                        "required": ["reminder_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "resume_reminder",
                    "description": "Resumes a specific paused reminder by its ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reminder_id": {
                                "type": "string",
                                "description": "The unique ID of the reminder to resume."
                            }
                        },
                        "required": ["reminder_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "update_reminder",
                    "description": "Updates the schedule of an existing reminder.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reminder_id": {
                                "type": "string",
                                "description": "The unique ID of the reminder to update."
                            },
                            "schedule_type": {
                                "type": "string",
                                "enum": ["daily", "interval"],
                                "description": "Whether the reminder is at a specific time daily or on an interval"
                            },
                            "time_value": {
                                "type": "string",
                                "description": "If schedule_type is 'daily', provide time in HH:MM format (24-hour). If 'interval', provide decimal hours."
                            }
                        },
                        "required": ["reminder_id", "schedule_type", "time_value"],
                    },
                },
            },
"""

# Find the end of get_tool_definitions list
log_adh_idx = content.find('"name": "log_adherence"')
end_bracket_idx = content.find("        ]", log_adh_idx)

content = content[:end_bracket_idx] + new_tools + content[end_bracket_idx:]

execute_tool_str = """
        elif tool_name == "list_reminders":
            return self.list_reminders(user_id)
        elif tool_name == "delete_reminder":
            return self.delete_reminder(user_id, args["reminder_id"])
        elif tool_name == "pause_reminder":
            return self.pause_reminder(user_id, args["reminder_id"])
        elif tool_name == "resume_reminder":
            return self.resume_reminder(user_id, args["reminder_id"])
        elif tool_name == "update_reminder":
            return self.update_reminder(user_id, args["reminder_id"], args["schedule_type"], args["time_value"])
"""

log_adh_exec_idx = content.find('elif tool_name == "log_adherence":')
content = content[:log_adh_exec_idx] + execute_tool_str + content[log_adh_exec_idx:]

# Rewrite set_reminder
old_set_reminder = """    def set_reminder(
        self, user_id: str, task: str, schedule_type: str, time_value: str
    ) -> dict[str, Any]:
        \"\"\"Sets a reminder using APScheduler.\"\"\"
        scheduler = get_scheduler()
        if not scheduler:
            return {"error": True, "message": "Scheduler not initialized"}

        content = f"Reminder: {task}. Reply 'Done' when you've finished."
        job_id = f"rem_{user_id}_{task.replace(' ', '_').lower()}"

        try:
            if schedule_type == "daily":
                hours, minutes = map(int, time_value.split(":"))
                trigger = CronTrigger(hour=hours, minute=minutes)
            elif schedule_type == "interval":
                hours = float(time_value)
                if hours < 0.25:
                    return {
                        "error": True,
                        "message": "Interval too short. Minimum interval is 0.25 hours (15 minutes).",
                    }
                trigger = IntervalTrigger(seconds=int(hours * 3600))
            else:
                return {
                    "error": True,
                    "message": f"Unknown schedule_type: {schedule_type}",
                }

            scheduler.add_job(
                send_scheduled_reminder,
                trigger=trigger,
                args=[user_id, "reminder", content],
                id=job_id,
                replace_existing=True,
            )

            try:
                engine = self.db.engine
                if engine is None:
                    raise RuntimeError("Database engine is not initialized")
                with engine.connect() as conn:
                    conn.execute(
                        text(
                            "INSERT INTO reminders (user_id, reminder_type, interval_expression) "
                            "VALUES (:uid, :type, :expr)"
                        ),
                        {
                            "uid": user_id,
                            "type": task,
                            "expr": f"{schedule_type}_{time_value}",
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
                "message": f"Reminder for '{task}' set successfully.",
            }
        except Exception as e:
            return {"error": True, "message": str(e)}"""

new_set_reminder = """    def set_reminder(
        self, user_id: str, task: str, schedule_type: str, time_value: str
    ) -> dict[str, Any]:
        \"\"\"Sets a reminder using APScheduler.\"\"\"
        scheduler = get_scheduler()
        if not scheduler:
            return {"error": True, "message": "Scheduler not initialized"}

        import uuid
        reminder_id = str(uuid.uuid4())
        job_id = f"rem_{reminder_id}"
        content = f"Reminder: {task}. Reply 'Done' when you've finished."

        try:
            if schedule_type == "daily":
                hours, minutes = map(int, time_value.split(":"))
                trigger = CronTrigger(hour=hours, minute=minutes)
            elif schedule_type == "interval":
                hours = float(time_value)
                if hours < 0.25:
                    return {
                        "error": True,
                        "message": "Interval too short. Minimum interval is 0.25 hours (15 minutes).",
                    }
                trigger = IntervalTrigger(seconds=int(hours * 3600))
            else:
                return {
                    "error": True,
                    "message": f"Unknown schedule_type: {schedule_type}",
                }

            scheduler.add_job(
                send_scheduled_reminder,
                trigger=trigger,
                args=[user_id, "reminder", content],
                id=job_id,
                replace_existing=True,
            )

            try:
                engine = self.db.engine
                if engine is None:
                    raise RuntimeError("Database engine is not initialized")
                with engine.connect() as conn:
                    conn.execute(
                        text(
                            "INSERT INTO reminders (user_id, job_id, reminder_type, interval_expression) "
                            "VALUES (:uid, :jid, :type, :expr)"
                        ),
                        {
                            "uid": user_id,
                            "jid": job_id,
                            "type": task,
                            "expr": f"{schedule_type}_{time_value}",
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

    def list_reminders(self, user_id: str) -> dict[str, Any]:
        \"\"\"Lists all active reminders for the user.\"\"\"
        engine = self.db.engine
        if engine is None:
            return {"error": True, "message": "Database not initialized"}
        
        try:
            with engine.connect() as conn:
                results = conn.execute(
                    text("SELECT job_id, reminder_type, interval_expression, is_active FROM reminders WHERE user_id = :uid AND is_active = 1"),
                    {"uid": user_id}
                ).fetchall()
                
            reminders = []
            for row in results:
                # job_id is like 'rem_UUID', we can return the UUID or the full job_id
                r_id = row.job_id.replace("rem_", "") if row.job_id else "unknown"
                reminders.append({
                    "id": r_id,
                    "task": row.reminder_type,
                    "schedule": row.interval_expression,
                    "active": bool(row.is_active)
                })
            
            return {
                "success": True,
                "reminders": reminders,
                "message": f"Found {len(reminders)} active reminders."
            }
        except Exception as e:
            return {"error": True, "message": str(e)}

    def delete_reminder(self, user_id: str, reminder_id: str) -> dict[str, Any]:
        \"\"\"Deletes a reminder from the scheduler and database.\"\"\"
        scheduler = get_scheduler()
        job_id = f"rem_{reminder_id}"
        
        # Remove from scheduler
        if scheduler and scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            
        # Remove from DB
        engine = self.db.engine
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

    def pause_reminder(self, user_id: str, reminder_id: str) -> dict[str, Any]:
        \"\"\"Pauses a reminder.\"\"\"
        scheduler = get_scheduler()
        job_id = f"rem_{reminder_id}"
        
        if scheduler and scheduler.get_job(job_id):
            scheduler.pause_job(job_id)
            
        engine = self.db.engine
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

    def resume_reminder(self, user_id: str, reminder_id: str) -> dict[str, Any]:
        \"\"\"Resumes a paused reminder.\"\"\"
        scheduler = get_scheduler()
        job_id = f"rem_{reminder_id}"
        
        if scheduler and scheduler.get_job(job_id):
            scheduler.resume_job(job_id)
            
        engine = self.db.engine
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

    def update_reminder(self, user_id: str, reminder_id: str, schedule_type: str, time_value: str) -> dict[str, Any]:
        \"\"\"Updates the schedule of an existing reminder.\"\"\"
        scheduler = get_scheduler()
        job_id = f"rem_{reminder_id}"
        
        # Get existing task to update scheduler content
        engine = self.db.engine
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
                    hours = float(time_value)
                    trigger = IntervalTrigger(seconds=int(hours * 3600))
                else:
                    return {"error": True, "message": f"Unknown schedule_type: {schedule_type}"}

                if scheduler:
                    # Update job trigger
                    content = f"Reminder: {task}. Reply 'Done' when you've finished."
                    scheduler.reschedule_job(job_id, trigger=trigger)
                
                # Update DB
                conn.execute(
                    text("UPDATE reminders SET interval_expression = :expr WHERE user_id = :uid AND job_id = :jid"),
                    {"expr": f"{schedule_type}_{time_value}", "uid": user_id, "jid": job_id}
                )
                conn.commit()
            return {"success": True, "message": f"Reminder {reminder_id} updated successfully."}
        except Exception as e:
            return {"error": True, "message": str(e)}"""

content = content.replace(old_set_reminder, new_set_reminder)

with open("app/tools.py", "w") as f:
    f.write(content)

print("All patched!")
