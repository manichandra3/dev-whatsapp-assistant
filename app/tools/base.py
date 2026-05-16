import json
import logging
from typing import Any

from app.database import DatabaseManager
from app.llm.providers import LLMProvider
from app.tools.definitions import get_tool_definitions
from app.tools.images import interpret_knee_image, parse_prescription_image
from app.tools.metrics import (
    RecoveryPhaseResult,
    build_user_context,
    get_recovery_phase,
    log_daily_metrics,
    set_surgery_date,
)
from app.tools.reminders import (
    delete_reminder,
    list_reminders,
    log_adherence,
    pause_reminder,
    resume_reminder,
    set_reminder,
    update_reminder,
)

logger = logging.getLogger(__name__)


class ACLRehabTools:
    def __init__(self, database: DatabaseManager, llm: LLMProvider | None = None) -> None:
        self.db = database
        self.llm = llm

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return get_tool_definitions()

    def get_recovery_phase(
        self, user_id: str, surgery_date: str | None = None
    ) -> RecoveryPhaseResult:
        return get_recovery_phase(self.db, user_id, surgery_date)

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
        return log_daily_metrics(self.db, user_id, pain_level, swelling_status, rom_extension, rom_flexion, adherence, notes)

    def set_surgery_date(
        self,
        user_id: str,
        surgery_date: str,
        surgeon_name: str | None = None,
        surgery_type: str = "ACL Reconstruction",
    ) -> dict[str, Any]:
        return set_surgery_date(self.db, user_id, surgery_date, surgeon_name, surgery_type)

    def build_user_context(self, user_id: str) -> str | None:
        return build_user_context(self.db, user_id)

    async def parse_prescription_image(self, user_id: str, media_id: str) -> dict[str, Any]:
        return await parse_prescription_image(self.db, self.llm, user_id, media_id)

    async def interpret_knee_image(self, user_id: str, media_id: str) -> dict[str, Any]:
        return await interpret_knee_image(self.db, self.llm, user_id, media_id)

    def set_reminder(self, user_id: str, task: str, schedule_type: str, time_value: str) -> dict[str, Any]:
        return set_reminder(self.db, user_id, task, schedule_type, time_value)

    def list_reminders(self, user_id: str) -> dict[str, Any]:
        return list_reminders(self.db, user_id)

    def delete_reminder(self, user_id: str, reminder_id: str) -> dict[str, Any]:
        return delete_reminder(self.db, user_id, reminder_id)

    def pause_reminder(self, user_id: str, reminder_id: str) -> dict[str, Any]:
        return pause_reminder(self.db, user_id, reminder_id)

    def resume_reminder(self, user_id: str, reminder_id: str) -> dict[str, Any]:
        return resume_reminder(self.db, user_id, reminder_id)

    def update_reminder(self, user_id: str, reminder_id: str, schedule_type: str, time_value: str) -> dict[str, Any]:
        return update_reminder(self.db, user_id, reminder_id, schedule_type, time_value)

    def log_adherence(self, user_id: str, task: str, status: str) -> dict[str, Any]:
        return log_adherence(self.db, user_id, task, status)

    async def execute_tool(
        self, tool_name: str, user_id: str, args: dict[str, Any]
    ) -> dict[str, Any]:
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
