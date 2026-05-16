import logging
from datetime import date
from sqlalchemy import text
from app.database import DatabaseManager

logger = logging.getLogger(__name__)

# Onboarding steps
STEP_START = 1
STEP_SURGERY_DATE = 2
STEP_BASELINE_PAIN = 3
STEP_GOAL = 4
STEP_TIMEZONE = 5
STEP_GAMIFICATION = 6
STEP_NOTIFICATION = 7
STEP_COMPLETE = 8

class OnboardingManager:
    def __init__(self, db: DatabaseManager):
        self.db = db
        
    def get_session(self, user_id: str) -> dict | None:
        with self.db.engine.connect() as conn:
            result = conn.execute(
                text("SELECT * FROM onboarding_sessions WHERE user_id = :user_id"),
                {"user_id": user_id}
            ).fetchone()
            if result:
                # Column order: user_id, current_step, surgery_date, baseline_pain, goal, timezone, gamification_opt_in, notification_freq, updated_at
                return {
                    "user_id": result[0],
                    "current_step": result[1],
                    "surgery_date": result[2],
                    "baseline_pain": result[3],
                    "goal": result[4],
                    "timezone": result[5],
                    "gamification_opt_in": bool(result[6]) if result[6] is not None else None,
                    "notification_freq": result[7],
                }
            return None

    def start_session(self, user_id: str):
        with self.db.engine.connect() as conn:
            conn.execute(
                text("""
                INSERT INTO onboarding_sessions (user_id, current_step) 
                VALUES (:user_id, 1)
                ON CONFLICT(user_id) DO UPDATE SET current_step = 1
                """),
                {"user_id": user_id}
            )
            conn.commit()

    def _update_session_field(self, user_id: str, field: str, value) -> None:
        """Update a single onboarding session field safely."""
        allowed = {
            "current_step", "surgery_date", "baseline_pain",
            "goal", "timezone", "gamification_opt_in", "notification_freq",
        }
        if field not in allowed:
            raise ValueError(f"Unknown onboarding field: {field}")
        val = value
        if field == "gamification_opt_in" and value is not None:
            val = 1 if bool(value) else 0
        with self.db.engine.connect() as conn:
            conn.execute(
                text(f"UPDATE onboarding_sessions SET {field} = :val, updated_at = DATETIME('now') WHERE user_id = :uid"),
                {"val": val, "uid": user_id},
            )
            conn.commit()

    def update_session(self, user_id: str, **kwargs):
        allowed = {
            "current_step", "surgery_date", "baseline_pain",
            "goal", "timezone", "gamification_opt_in", "notification_freq",
        }
        for key, value in kwargs.items():
            if key in allowed:
                self._update_session_field(user_id, key, value)



    def complete_session(self, user_id: str):
        session = self.get_session(user_id)
        if not session:
            return

        # Ensure gamification_opt_in is properly typed (default to opt-out if None)
        gamification_opt_in = session.get("gamification_opt_in")
        if gamification_opt_in is None:
            gamification_opt_in = False

        surgery_date = session.get("surgery_date") or date.today().isoformat()

        # Update user config
        with self.db.engine.connect() as conn:
            conn.execute(
                text("""
                UPDATE user_config
                SET surgery_date = :surgery_date,
                    timezone = :timezone,
                    gamification_opt_in = :gamification_opt_in,
                    goals = :goals,
                    notification_freq = :notification_freq
                WHERE user_id = :user_id
                """),
                {
                    "user_id": user_id,
                    "surgery_date": surgery_date,
                    "timezone": session["timezone"] or "UTC",
                    "gamification_opt_in": 1 if gamification_opt_in else 0,
                    "goals": session["goal"],
                    "notification_freq": session.get("notification_freq"),
                }
            )
            
            # Delete session to mark as complete
            conn.execute(text("DELETE FROM onboarding_sessions WHERE user_id = :user_id"), {"user_id": user_id})
            conn.commit()
        
    def handle_message(self, user_id: str, message: str) -> str | None:
        """Returns string response if handled by onboarding, else None"""
        session = self.get_session(user_id)

        if not session:
            # Check if user needs onboarding (no user_config exists)
            user_config = self.db.get_user_config(user_id)
            if not user_config:
                # Start onboarding for new user
                self.db.set_surgery_date(user_id, "PENDING")
                self.start_session(user_id)
                return "Hi — I help guide your ACL rehab. Can I ask a few setup questions? Reply Yes to continue."
            else:
                # User exists but not in onboarding - normal flow
                return None
                
        step = session["current_step"]
        msg = message.strip().lower()
        
        if step == STEP_START:
            if msg in ["yes", "y", "sure", "ok"]:
                self.update_session(user_id, current_step=STEP_SURGERY_DATE)
                return "Great! When was your ACL surgery? (Please reply in YYYY-MM-DD format)"
            else:
                return "No problem! When you're ready to start, just say 'yes'."
                
        elif step == STEP_SURGERY_DATE:
            # simple validation
            import re
            if re.match(r"^\d{4}-\d{2}-\d{2}$", msg):
                self.update_session(user_id, surgery_date=msg, current_step=STEP_BASELINE_PAIN)
                return "Got it. On a scale of 0-10, what is your current baseline pain level?"
            else:
                return "I couldn't understand that date. Please use YYYY-MM-DD format (e.g., 2026-04-15)."
                
        elif step == STEP_BASELINE_PAIN:
            if msg.isdigit() and 0 <= int(msg) <= 10:
                self.update_session(user_id, baseline_pain=int(msg), current_step=STEP_GOAL)
                return "What is your primary goal right now? (e.g. Restore ROM, Return to sport, Reduce pain)"
            else:
                return "Please reply with a number between 0 and 10."
                
        elif step == STEP_GOAL:
            self.update_session(user_id, goal=message.strip(), current_step=STEP_TIMEZONE)
            return "What timezone are you in? (e.g. UTC, America/New_York)"
            
        elif step == STEP_TIMEZONE:
            self.update_session(user_id, timezone=message.strip(), current_step=STEP_GAMIFICATION)
            return "We have an optional gamification feature (streaks, badges, charts) to keep you motivated. Reply 1 to opt in, 2 to skip."
            
        elif step == STEP_GAMIFICATION:
            if msg in ["1", "yes", "opt in", "y"]:
                self.update_session(user_id, gamification_opt_in=True, current_step=STEP_NOTIFICATION)
                return "You're opted in! How often do you want reminders? (e.g. Daily, 3x/week)"
            elif msg in ["2", "no", "skip", "n"]:
                self.update_session(user_id, gamification_opt_in=False, current_step=STEP_NOTIFICATION)
                return "No problem, you're opted out. How often do you want reminders? (e.g. Daily, 3x/week)"
            else:
                return "Please reply 1 to opt in or 2 to skip."
                
        elif step == STEP_NOTIFICATION:
            self.update_session(user_id, notification_freq=message.strip(), current_step=STEP_COMPLETE)
            self.complete_session(user_id)
            return "All set! You're ready to begin your recovery journey. Let me know when you complete your first set of exercises."
            
        return None
