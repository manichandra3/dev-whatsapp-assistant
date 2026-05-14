"""
ACL Rehab Tools - Function tools for the LLM agent

Provides structured tools that the LLM can call to:
1. Log daily metrics
2. Get recovery phase information
3. Access patient history
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import text

from app.database import DatabaseManager
from app.scheduler import get_scheduler, send_scheduled_reminder

logger = logging.getLogger(__name__)


@dataclass
class RecoveryPhaseResult:
    """Result of get_recovery_phase calculation."""

    error: bool = False
    message: str | None = None
    weeks_post_op: int | None = None
    days_post_op: int | None = None
    phase: str | None = None
    phase_name: str | None = None
    surgery_date: str | None = None
    recommended_exercises: list[str] | None = None
    precautions: list[str] | None = None
    goals: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        if self.error:
            return {"error": True, "message": self.message}
        return {
            "success": True,
            "weeksPostOp": self.weeks_post_op,
            "daysPostOp": self.days_post_op,
            "phase": self.phase,
            "phaseName": self.phase_name,
            "surgeryDate": self.surgery_date,
            "recommendedExercises": self.recommended_exercises,
            "precautions": self.precautions,
            "goals": self.goals,
        }


class ACLRehabTools:
    """Tool implementations for ACL rehabilitation coaching."""

    def __init__(self, database: DatabaseManager, llm=None) -> None:
        self.db = database
        self.llm = llm

    def get_recovery_phase(
        self, user_id: str, surgery_date: str | None = None
    ) -> RecoveryPhaseResult:
        """
        Get recovery phase based on surgery date.

        Calculates the current recovery phase and returns phase-specific
        exercise recommendations, precautions, and goals.
        """
        # Get surgery date from database if not provided
        if not surgery_date:
            user_config = self.db.get_user_config(user_id)
            if not user_config or not user_config.surgery_date:
                return RecoveryPhaseResult(
                    error=True,
                    message="Surgery date not configured. Please set your surgery date first.",
                )
            surgery_date = user_config.surgery_date

        surgery = datetime.strptime(surgery_date, "%Y-%m-%d").date()
        today = date.today()
        days_diff = (today - surgery).days
        weeks_post_op = days_diff // 7

        phase: str
        phase_name: str
        recommended_exercises: list[str]
        precautions: list[str]
        goals: list[str]

        if weeks_post_op < 2:
            # Phase 1: 0-2 weeks
            phase = "Phase 1"
            phase_name = "Protection & Initial Recovery"
            recommended_exercises = [
                "Ankle pumps (20 reps every hour while awake)",
                "Quad sets (10 reps, 3 sets per day)",
                "Straight leg raises (10 reps, 3 sets per day)",
                "Heel slides (10 reps, 3 sets per day)",
                "Passive knee extension (3 times daily, 10 min each)",
            ]
            precautions = [
                "Weight bearing as tolerated with crutches",
                "Keep leg elevated when resting",
                "Ice 15-20 minutes every 2-3 hours",
                "NO active knee flexion beyond 90°",
                "Avoid pivoting or twisting motions",
            ]
            goals = [
                "Reduce swelling and pain",
                "Achieve full passive extension (0°)",
                "Reach 90° flexion",
                "Independent straight leg raise",
            ]

        elif weeks_post_op < 6:
            # Phase 2: 2-6 weeks
            phase = "Phase 2"
            phase_name = "Early Strengthening"
            recommended_exercises = [
                "Continue Phase 1 exercises",
                "Mini squats (0-45°, 10 reps, 3 sets)",
                "Step-ups (4-inch step, 10 reps, 3 sets)",
                "Wall sits (hold 20-30 seconds, 3 sets)",
                "Stationary bike (light resistance, 10-15 min)",
                "Hamstring curls (light resistance)",
                "Calf raises (10 reps, 3 sets)",
            ]
            precautions = [
                "Progress to full weight bearing",
                "Wean off crutches as tolerated",
                "Continue ice after exercise",
                "Avoid deep squats (>90°)",
                "No running or jumping",
            ]
            goals = [
                "Full weight bearing without crutches",
                "Achieve 120° flexion",
                "Normalize gait pattern",
                "Reduce swelling to minimal",
            ]

        elif weeks_post_op < 12:
            # Phase 3: 6-12 weeks
            phase = "Phase 3"
            phase_name = "Progressive Loading"
            recommended_exercises = [
                "Single-leg mini squats (10 reps, 3 sets)",
                "Leg press (progressive resistance)",
                "Step-downs (6-inch step, 10 reps, 3 sets)",
                "Balance exercises (single leg, 30 seconds, 3 sets)",
                "Elliptical trainer (15-20 min)",
                "Lateral band walks (10 steps each direction, 3 sets)",
                "Nordic hamstring curls (eccentric focus)",
            ]
            precautions = [
                "Progress resistance gradually",
                "Continue ice after intense exercise",
                "NO running until cleared by surgeon (typically 12+ weeks)",
                "Avoid cutting/pivoting movements",
                "Monitor for increased swelling or pain",
            ]
            goals = [
                "Full range of motion (0-135°)",
                "75% quadriceps strength compared to uninjured leg",
                "Good single-leg balance",
                "Prepare for running progression",
            ]

        else:
            # Phase 4: 3+ months
            phase = "Phase 4"
            phase_name = "Return to Sport Preparation"
            recommended_exercises = [
                "Running progression (start with straight-line jogging)",
                "Plyometric exercises (box jumps, single-leg hops)",
                "Agility drills (cone drills, ladder drills)",
                "Sport-specific movements",
                "Advanced strength training (squats, deadlifts, lunges)",
                "Balance and proprioception challenges",
            ]
            precautions = [
                "Progress only with surgeon/PT approval",
                "Complete return-to-sport testing before full clearance",
                "Monitor for any knee instability",
                "Gradual return to sport-specific activities",
                "Consider ACL injury prevention program ongoing",
            ]
            goals = [
                "90%+ quadriceps and hamstring strength symmetry",
                "Pass hop tests (>90% limb symmetry)",
                "Psychological readiness for sport",
                "Full clearance from medical team",
            ]

        return RecoveryPhaseResult(
            weeks_post_op=weeks_post_op,
            days_post_op=days_diff,
            phase=phase,
            phase_name=phase_name,
            surgery_date=surgery_date,
            recommended_exercises=recommended_exercises,
            precautions=precautions,
            goals=goals,
        )

    def log_daily_metrics(
        self,
        user_id: str,
        pain_level: int,
        swelling_status: str,
        rom_extension: int,
        rom_flexion: int,
        adherence: bool,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Log daily metrics - wrapper for database method."""
        result = self.db.log_daily_metrics(
            user_id=user_id,
            pain_level=pain_level,
            swelling_status=swelling_status,
            rom_extension=rom_extension,
            rom_flexion=rom_flexion,
            adherence=adherence,
            notes=notes,
        )
        return {
            "success": result.success,
            "message": result.message,
            "data": result.data,
        }

    def set_surgery_date(
        self,
        user_id: str,
        surgery_date: str,
        surgeon_name: str | None = None,
        surgery_type: str = "ACL Reconstruction",
    ) -> dict[str, Any]:
        # Validate date format
        try:
            parsed_date = datetime.strptime(surgery_date, "%Y-%m-%d").date()
        except ValueError:
            return {
                "success": False,
                "error": True,
                "message": f"Invalid date format: '{surgery_date}'. Please use YYYY-MM-DD format (e.g., 2026-01-15).",
            }

        # Check if date is reasonable (not too far in past or future)
        today = date.today()
        days_diff = (today - parsed_date).days

        if days_diff < -365:  # More than 1 year in future
            return {
                "success": False,
                "error": True,
                "message": f"Surgery date {surgery_date} is more than a year in the future. Please verify the date.",
            }

        if days_diff > 730:  # More than 2 years in past
            return {
                "success": False,
                "error": True,
                "message": f"Surgery date {surgery_date} is more than 2 years ago. ACL rehab coaching is most relevant within 2 years post-op.",
            }

        # Store in database
        self.db.set_surgery_date(user_id, surgery_date, surgeon_name, surgery_type)

        # Calculate current phase for confirmation
        weeks_post_op = days_diff // 7 if days_diff >= 0 else 0

        if days_diff < 0:
            phase_info = f"Your surgery is scheduled in {-days_diff} days."
        else:
            phase_info = f"You are {weeks_post_op} weeks post-op."

        return {
            "success": True,
            "message": f"✅ Surgery date set to {surgery_date}. {phase_info}",
            "data": {
                "surgeryDate": surgery_date,
                "surgeonName": surgeon_name,
                "surgeryType": surgery_type,
                "weeksPostOp": weeks_post_op if days_diff >= 0 else None,
                "daysPostOp": days_diff if days_diff >= 0 else None,
            },
        }

    def build_user_context(self, user_id: str) -> str | None:
        """Build context string with user's surgery date and latest metrics for LLM injection."""
        context_parts = []

        user_config = self.db.get_user_config(user_id)
        if user_config and user_config.surgery_date:
            try:
                surgery = datetime.strptime(user_config.surgery_date, "%Y-%m-%d").date()
                today = date.today()
                days_post_op = (today - surgery).days
                weeks_post_op = days_post_op // 7

                if days_post_op >= 0:
                    if weeks_post_op < 2:
                        phase = "Phase 1 (Protection & Initial Recovery)"
                    elif weeks_post_op < 6:
                        phase = "Phase 2 (Early Strengthening)"
                    elif weeks_post_op < 12:
                        phase = "Phase 3 (Progressive Loading)"
                    else:
                        phase = "Phase 4 (Return to Sport Preparation)"

                    context_parts.append(
                        f"[USER CONTEXT]\n"
                        f"Surgery Date: {user_config.surgery_date}\n"
                        f"Days Post-Op: {days_post_op}\n"
                        f"Weeks Post-Op: {weeks_post_op}\n"
                        f"Current Phase: {phase}"
                    )
                else:
                    context_parts.append(
                        f"[USER CONTEXT]\n"
                        f"Scheduled Surgery Date: {user_config.surgery_date}\n"
                        f"Days Until Surgery: {-days_post_op}"
                    )

                if user_config.surgeon_name:
                    context_parts.append(f"Surgeon: {user_config.surgeon_name}")
                if user_config.surgery_type:
                    context_parts.append(f"Surgery Type: {user_config.surgery_type}")

            except ValueError:
                pass

        latest_metrics = self.db.get_latest_metrics(user_id)
        if latest_metrics:
            context_parts.append(
                f"\n[LATEST CHECK-IN ({latest_metrics.date})]\n"
                f"Pain Level: {latest_metrics.pain_level}/10\n"
                f"Swelling: {latest_metrics.swelling_status}\n"
                f"ROM Extension: {latest_metrics.rom_extension}°\n"
                f"ROM Flexion: {latest_metrics.rom_flexion}°\n"
                f"Exercise Adherence: {'Yes' if latest_metrics.adherence else 'No'}"
            )
            if latest_metrics.notes:
                context_parts.append(f"Notes: {latest_metrics.notes}")

        trends = self.db.get_metrics_trends(user_id, 7)
        if trends:
            trend_str = []
            if trends.pain_trend != 0:
                trend_str.append(
                    f"Pain {'↑' if trends.pain_trend > 0 else '↓'}{abs(trends.pain_trend)}"
                )
            if trends.rom_flexion_trend != 0:
                trend_str.append(
                    f"Flexion {'↑' if trends.rom_flexion_trend > 0 else '↓'}{abs(trends.rom_flexion_trend)}°"
                )
            if trends.adherence_rate < 1.0:
                trend_str.append(f"Adherence: {trends.adherence_rate:.0%}")
            if trend_str:
                context_parts.append(f"7-Day Trends: {', '.join(trend_str)}")

        return "\n".join(context_parts) if context_parts else None

    async def parse_prescription_image(self, user_id: str, media_id: str) -> dict[str, Any]:
        """Parse prescription image to extract medications and schedules."""
        if not self.llm:
            return {"error": True, "message": "LLM provider not configured for image analysis."}
            
        try:
            with self.db.engine.connect() as conn:
                from sqlalchemy import text
                result = conn.execute(
                    text("SELECT path FROM media WHERE id = :id AND user_id = :uid"),
                    {"id": media_id, "uid": user_id}
                ).fetchone()
                
            if not result:
                return {"error": True, "message": f"Media ID {media_id} not found."}
                
            image_path = result[0]
            
            prompt = """You are a medical data extraction assistant. 
Please carefully read this prescription/medication label and extract the following details in JSON format.
If you cannot find a detail, use null.
The output MUST be valid JSON matching this schema exactly:
{
    "meds": [
        {
            "name": "string (name of medication)",
            "dose": "string (e.g. 500mg)",
            "frequency": "string (e.g. twice daily, q12h)",
            "duration": "string (e.g. 7 days)",
            "raw_text": "string (the exact text snippet you found this in)"
        }
    ],
    "suggestions": ["string (e.g. 'Set a reminder for twice daily', 'Ensure taken with food')"]
}
Do not include any text outside the JSON."""

            response_text = await self.llm.analyze_image(image_path, prompt)
            
            # Extract JSON block
            import json
            import re
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # try to find anything that looks like JSON
                json_match = re.search(r'(\{.*\})', response_text, re.DOTALL)
                json_str = json_match.group(1) if json_match else response_text

            parsed_data = json.loads(json_str)
            
            # Save the parse result
            with self.db.engine.connect() as conn:
                conn.execute(
                    text(
                        "INSERT INTO prescription_parses (user_id, media_id, raw_text, parsed_json) "
                        "VALUES (:uid, :mid, :raw, :json)"
                    ),
                    {"uid": user_id, "mid": media_id, "raw": response_text, "json": json.dumps(parsed_data)}
                )
                conn.commit()
                
            return {
                "success": True,
                "parsed_data": parsed_data,
                "message": f"Successfully parsed prescription. Found {len(parsed_data.get('meds', []))} medications."
            }
            
        except Exception as e:
            logger.error(f"[TOOL] Error parsing prescription: {e}")
            return {"error": True, "message": str(e)}

    async def interpret_knee_image(self, user_id: str, media_id: str) -> dict[str, Any]:
        """Interpret a knee image for recovery progress and red flags."""
        if not self.llm:
            return {"error": True, "message": "LLM provider not configured for image analysis."}
            
        try:
            with self.db.engine.connect() as conn:
                from sqlalchemy import text
                result = conn.execute(
                    text("SELECT path FROM media WHERE id = :id AND user_id = :uid"),
                    {"id": media_id, "uid": user_id}
                ).fetchone()
                
            if not result:
                return {"error": True, "message": f"Media ID {media_id} not found."}
                
            image_path = result[0]
            
            prompt = """You are an ACL rehabilitation assistant. 
Please look at this image of a knee post-surgery.
You must NEVER provide a definitive medical diagnosis. Provide OBSERVATIONS ONLY.

Evaluate the image for:
1. Dressing status (is it covered, exposed, clean, soiled?)
2. Visible redness (erythema)
3. Swelling (compare to surrounding tissue if possible)
4. Bruising (ecchymosis)
5. Any visible drainage or discharge
6. Overall impression

Output MUST be valid JSON:
{
    "observations": [
        "Observation 1",
        "Observation 2"
    ],
    "flags": [
        "Any red flags (e.g. extreme redness, purulent drainage). Empty array if none."
    ],
    "confidence": "high|medium|low"
}
Do not include any text outside the JSON."""

            response_text = await self.llm.analyze_image(image_path, prompt)
            
            import json
            import re
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_match = re.search(r'(\{.*\})', response_text, re.DOTALL)
                json_str = json_match.group(1) if json_match else response_text

            parsed_data = json.loads(json_str)
            
            return {
                "success": True,
                "data": parsed_data,
                "message": "Successfully interpreted knee image. Please review the observations and flags."
            }
            
        except Exception as e:
            logger.error(f"[TOOL] Error interpreting knee image: {e}")
            return {"error": True, "message": str(e)}
    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get formatted tools list for LLM."""
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

    async def execute_tool(
        self, tool_name: str, user_id: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a tool call from the LLM."""
        if tool_name == "parse_prescription_image":
            return await self.parse_prescription_image(user_id, args["media_id"])
        elif tool_name == "interpret_knee_image":
            return await self.interpret_knee_image(user_id, args["media_id"])
        elif tool_name == "set_surgery_date":
            return self.set_surgery_date(
                user_id=user_id,
                surgery_date=args["surgery_date"],
                surgeon_name=args.get("surgeon_name"),
                surgery_type=args.get("surgery_type", "ACL Reconstruction"),
            )
        elif tool_name == "log_daily_metrics":
            return self.log_daily_metrics(
                user_id=user_id,
                pain_level=args["pain_level"],
                swelling_status=args["swelling_status"],
                rom_extension=args["rom_extension"],
                rom_flexion=args["rom_flexion"],
                adherence=args["adherence"],
                notes=args.get("notes"),
            )
        elif tool_name == "get_recovery_phase":
            result = self.get_recovery_phase(user_id)
            return result.to_dict()
        elif tool_name == "set_reminder":
            return self.set_reminder(
                user_id=user_id,
                task=args["task"],
                schedule_type=args["schedule_type"],
                time_value=args["time_value"],
            )
        
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
        elif tool_name == "log_adherence":
            return self.log_adherence(
                user_id=user_id, task=args["task"], status=args["status"]
            )
        else:
            return {"error": True, "message": f"Unknown tool: {tool_name}"}

    def set_reminder(
        self, user_id: str, task: str, schedule_type: str, time_value: str
    ) -> dict[str, Any]:
        """Sets a reminder using APScheduler."""
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
        """Lists all active reminders for the user with friendly schedule descriptions."""
        engine = self.db.engine
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
                            # Next run time handling
                            nrt = job.next_run_time
                            if nrt is None:
                                next_run = "Paused"
                            else:
                                try:
                                    next_run = nrt.isoformat()
                                except Exception:
                                    next_run = str(nrt)

                            # Friendly trigger description
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

    def delete_reminder(self, user_id: str, reminder_id: str) -> dict[str, Any]:
        """Deletes a reminder from the scheduler and database."""
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
        """Pauses a reminder."""
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
        """Resumes a paused reminder."""
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
        """Updates the schedule of an existing reminder."""
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
                    interval_hours = float(time_value)
                    trigger = IntervalTrigger(seconds=int(interval_hours * 3600))
                else:
                    return {"error": True, "message": f"Unknown schedule_type: {schedule_type}"}

                if scheduler:
                    # Update job trigger and args
                    content = f"Reminder: {task}. Reply 'Done' when you've finished."
                    scheduler.modify_job(job_id, args=[user_id, "reminder", content])
                    scheduler.reschedule_job(job_id, trigger=trigger)
                
                # Update DB
                conn.execute(
                    text("UPDATE reminders SET interval_expression = :expr WHERE user_id = :uid AND job_id = :jid"),
                    {"expr": f"{schedule_type}_{time_value}", "uid": user_id, "jid": job_id}
                )
                conn.commit()
            return {"success": True, "message": f"Reminder {reminder_id} updated successfully."}
        except Exception as e:
            return {"error": True, "message": str(e)}

    def log_adherence(self, user_id: str, task: str, status: str) -> dict[str, Any]:
        """Logs adherence to a task."""
        success = self.db.log_adherence(
            user_id=user_id, reminder_type=task, status=status
        )
        if success:
            return {
                "success": True,
                "message": f"Successfully logged {status} for {task}.",
            }
        return {"error": True, "message": "Failed to log adherence in database."}
