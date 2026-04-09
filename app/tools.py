"""
ACL Rehab Tools - Function tools for the LLM agent

Provides structured tools that the LLM can call to:
1. Log daily metrics
2. Get recovery phase information
3. Access patient history
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.database import DatabaseManager


@dataclass
class RecoveryPhaseResult:
    """Result of get_recovery_phase calculation."""

    success: bool = True
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
            "success": self.success,
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

    def __init__(self, database: DatabaseManager) -> None:
        self.db = database

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
                    success=False,
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

        elif weeks_post_op >= 2 and weeks_post_op < 6:
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

        elif weeks_post_op >= 6 and weeks_post_op < 12:
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
            success=True,
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
        """
        Set or update the user's surgery date.

        Args:
            user_id: WhatsApp user ID
            surgery_date: Surgery date in YYYY-MM-DD format
            surgeon_name: Optional surgeon name
            surgery_type: Type of surgery (default: ACL Reconstruction)

        Returns:
            Success/error result with confirmation message
        """
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

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get formatted tools list for LLM."""
        return [
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
        ]

    async def execute_tool(
        self, tool_name: str, user_id: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a tool call from the LLM."""
        if tool_name == "set_surgery_date":
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
        else:
            return {"error": True, "message": f"Unknown tool: {tool_name}"}
