import re
import sys

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
                                "description": "If schedule_type is 'daily', provide time in HH:MM format (24-hour). If 'interval', provide decimal hours (minimum 0.25)."
                            }
                        },
                        "required": ["reminder_id", "schedule_type", "time_value"],
                    },
                },
            },
"""

# Insert new_tools before the closing bracket of the return list in get_tool_definitions
parts = content.split('                    "name": "log_adherence",')
if len(parts) == 2:
    # We want to insert the new tools before the log_adherence tool.
    pass

# Or just use regex to replace log_adherence block
log_adh_pattern = r'(\{\s*"type": "function",\s*"function": \{\s*"name": "log_adherence".*?\}\s*\},?)'
match = re.search(log_adh_pattern, content, re.DOTALL)
if match:
    replacement = match.group(1) + "\n" + new_tools
    content = content.replace(match.group(1), replacement)

    with open("app/tools.py", "w") as f:
        f.write(content)
    print("Patched tool definitions.")
else:
    print("Could not find log_adherence block.")
