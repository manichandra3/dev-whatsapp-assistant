from typing import Any


def get_tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "parse_prescription_image",
                "description": "Parse a prescription or medication label image to extract medication names, doses, frequencies, and durations. Call this when the user uploads an image of a prescription.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "media_id": {
                            "type": "string",
                            "description": "The media ID of the uploaded image (found in the message context)."
                        }
                    },
                    "required": ["media_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "interpret_knee_image",
                "description": "Interpret an image of a knee post-surgery to provide observations on swelling, redness, dressing, and flag potential issues. Call this when the user uploads an image of their knee.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "media_id": {
                            "type": "string",
                            "description": "The media ID of the uploaded image (found in the message context)."
                        }
                    },
                    "required": ["media_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "set_surgery_date",
                "description": "Sets or updates the patient's ACL surgery date. Call this when the user mentions their surgery date for the first time or wants to update it. The date is required to calculate recovery phase and provide appropriate exercise recommendations.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "surgery_date": {
                            "type": "string",
                            "description": "The date of ACL surgery in YYYY-MM-DD format (e.g., 2026-01-15)",
                        },
                        "surgeon_name": {
                            "type": "string",
                            "description": "Optional name of the surgeon who performed the surgery",
                        },
                        "surgery_type": {
                            "type": "string",
                            "description": "Type of surgery performed (default: ACL Reconstruction)",
                            "default": "ACL Reconstruction",
                        },
                    },
                    "required": ["surgery_date"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "log_daily_metrics",
                "description": "Records the patient's daily check-in metrics including pain, swelling, range of motion, and exercise adherence. MUST be called after collecting daily check-in data.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pain_level": {
                            "type": "number",
                            "description": "Current pain level on a scale of 0-10, where 0 is no pain and 10 is worst imaginable pain",
                            "minimum": 0,
                            "maximum": 10,
                        },
                        "swelling_status": {
                            "type": "string",
                            "enum": ["worse", "same", "better"],
                            "description": "Current swelling status compared to yesterday",
                        },
                        "rom_extension": {
                            "type": "number",
                            "description": "Range of motion for knee extension in degrees (0 = fully straight)",
                            "minimum": -10,
                            "maximum": 30,
                        },
                        "rom_flexion": {
                            "type": "number",
                            "description": "Range of motion for knee flexion in degrees (typically 0-140)",
                            "minimum": 0,
                            "maximum": 160,
                        },
                        "adherence": {
                            "type": "boolean",
                            "description": "Whether the patient completed their prescribed exercises today",
                        },
                        "notes": {
                            "type": "string",
                            "description": "Optional additional notes about today's check-in",
                        },
                    },
                    "required": [
                        "pain_level",
                        "swelling_status",
                        "rom_extension",
                        "rom_flexion",
                        "adherence",
                    ],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_recovery_phase",
                "description": "Calculates the current recovery phase based on weeks post-op and returns phase-specific exercise recommendations, precautions, and goals. Call this BEFORE providing exercise advice.",
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
                "name": "set_reminder",
                "description": "Sets a proactive reminder for medication, water, or other tasks. Automatically appends 'Reply Done' to prompt user interaction.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "The task to remind the user about (e.g. 'Take Ibuprofen', 'Drink Water')",
                        },
                        "schedule_type": {
                            "type": "string",
                            "enum": ["daily", "interval"],
                            "description": "Whether the reminder is at a specific time daily or on an interval",
                        },
                        "time_value": {
                            "type": "string",
                            "description": "If schedule_type is 'daily', provide time in HH:MM format (24-hour). If 'interval', provide decimal hours (minimum 0.25, e.g. '2.5' for every 2.5 hours).",
                        },
                    },
                    "required": ["task", "schedule_type", "time_value"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "log_adherence",
                "description": "Logs when the user replies 'Done' to a proactive reminder (like taking medication or doing a task).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "The task that the user completed (e.g. 'Take Ibuprofen')",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["completed", "missed"],
                            "description": "Status of the task. Usually 'completed' if they replied 'Done'.",
                        },
                    },
                    "required": ["task", "status"],
                },
            },
        },
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
    ]
