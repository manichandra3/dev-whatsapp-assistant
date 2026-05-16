import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.database import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class RecoveryPhaseResult:
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


def get_recovery_phase(
    db: DatabaseManager, user_id: str, surgery_date: str | None = None
) -> RecoveryPhaseResult:
    if not surgery_date:
        user_config = db.get_user_config(user_id)
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
            "NO active knee flexion beyond 90deg",
            "Avoid pivoting or twisting motions",
        ]
        goals = [
            "Reduce swelling and pain",
            "Achieve full passive extension (0deg)",
            "Reach 90deg flexion",
            "Independent straight leg raise",
        ]

    elif weeks_post_op < 6:
        phase = "Phase 2"
        phase_name = "Early Strengthening"
        recommended_exercises = [
            "Continue Phase 1 exercises",
            "Mini squats (0-45deg, 10 reps, 3 sets)",
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
            "Avoid deep squats (>90deg)",
            "No running or jumping",
        ]
        goals = [
            "Full weight bearing without crutches",
            "Achieve 120deg flexion",
            "Normalize gait pattern",
            "Reduce swelling to minimal",
        ]

    elif weeks_post_op < 12:
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
            "Full range of motion (0-135deg)",
            "75% quadriceps strength compared to uninjured leg",
            "Good single-leg balance",
            "Prepare for running progression",
        ]

    else:
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
    db: DatabaseManager,
    user_id: str,
    pain_level: int,
    swelling_status: str,
    rom_extension: int,
    rom_flexion: int,
    adherence: bool,
    notes: str | None = None,
) -> dict[str, Any]:
    result = db.log_daily_metrics(
        user_id=user_id,
        pain_level=pain_level,
        swelling_status=swelling_status,
        rom_extension=rom_extension,
        rom_flexion=rom_flexion,
        adherence=adherence,
        notes=notes,
    )
    adherence_str = "Completed" if adherence else "Not done"
    formatted_message = (
        f"Metrics logged successfully!\n\n"
        f"Today's Check-in:\n"
        f"Pain: {pain_level}/10\n"
        f"Swelling: {swelling_status}\n"
        f"ROM: {rom_extension}deg extension, {rom_flexion}deg flexion\n"
        f"Exercises: {adherence_str}"
    )
    return {
        "success": result.success,
        "message": formatted_message,
        "data": result.data,
    }


def set_surgery_date(
    db: DatabaseManager,
    user_id: str,
    surgery_date: str,
    surgeon_name: str | None = None,
    surgery_type: str = "ACL Reconstruction",
) -> dict[str, Any]:
    try:
        parsed_date = datetime.strptime(surgery_date, "%Y-%m-%d").date()
    except ValueError:
        return {
            "success": False,
            "error": True,
            "message": f"Invalid date format: '{surgery_date}'. Please use YYYY-MM-DD format (e.g., 2026-01-15).",
        }

    today = date.today()
    days_diff = (today - parsed_date).days

    if days_diff < -365:
        return {
            "success": False,
            "error": True,
            "message": f"Surgery date {surgery_date} is more than a year in the future. Please verify the date.",
        }

    if days_diff > 730:
        return {
            "success": False,
            "error": True,
            "message": f"Surgery date {surgery_date} is more than 2 years ago. ACL rehab coaching is most relevant within 2 years post-op.",
        }

    db.set_surgery_date(user_id, surgery_date, surgeon_name, surgery_type)

    weeks_post_op = days_diff // 7 if days_diff >= 0 else 0

    if days_diff < 0:
        phase_info = f"Your surgery is scheduled in {-days_diff} days."
    else:
        phase_info = f"You are {weeks_post_op} weeks post-op."

    return {
        "success": True,
        "message": f"Surgery date set to {surgery_date}. {phase_info}",
        "data": {
            "surgeryDate": surgery_date,
            "surgeonName": surgeon_name,
            "surgeryType": surgery_type,
            "weeksPostOp": weeks_post_op if days_diff >= 0 else None,
            "daysPostOp": days_diff if days_diff >= 0 else None,
        },
    }


def build_user_context(db: DatabaseManager, user_id: str) -> str | None:
    context_parts = []

    user_config = db.get_user_config(user_id)
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

    latest_metrics = db.get_latest_metrics(user_id)
    if latest_metrics:
        context_parts.append(
            f"\n[LATEST CHECK-IN ({latest_metrics.date})]\n"
            f"Pain Level: {latest_metrics.pain_level}/10\n"
            f"Swelling: {latest_metrics.swelling_status}\n"
            f"ROM Extension: {latest_metrics.rom_extension}deg\n"
            f"ROM Flexion: {latest_metrics.rom_flexion}deg\n"
            f"Exercise Adherence: {'Yes' if latest_metrics.adherence else 'No'}"
        )
        if latest_metrics.notes:
            context_parts.append(f"Notes: {latest_metrics.notes}")

    trends = db.get_metrics_trends(user_id, 7)
    if trends:
        trend_str = []
        if trends.pain_trend != 0:
            trend_str.append(
                f"Pain {'up' if trends.pain_trend > 0 else 'down'}{abs(trends.pain_trend)}"
            )
        if trends.rom_flexion_trend != 0:
            trend_str.append(
                f"Flexion {'up' if trends.rom_flexion_trend > 0 else 'down'}{abs(trends.rom_flexion_trend)}deg"
            )
        if trends.adherence_rate < 1.0:
            trend_str.append(f"Adherence: {trends.adherence_rate:.0%}")
        if trend_str:
            context_parts.append(f"7-Day Trends: {', '.join(trend_str)}")

    return "\n".join(context_parts) if context_parts else None
