"""
Database and Tools Test Suite

Tests for database operations and tool execution.
"""

import os
import tempfile
from datetime import date, timedelta

import pytest

from app.database import DatabaseManager
from app.tools import ACLRehabTools


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = DatabaseManager(db_path)
        yield db
        db.close()


@pytest.fixture
def tools(temp_db: DatabaseManager) -> ACLRehabTools:
    """Create tools instance with temporary database."""
    return ACLRehabTools(temp_db)


class TestDatabaseManager:
    """Tests for DatabaseManager class."""

    def test_initialization(self, temp_db: DatabaseManager) -> None:
        """Test database initialization creates tables."""
        # Should be able to query tables without error
        metrics = temp_db.get_latest_metrics("test_user")
        assert metrics is None  # No data yet

    def test_set_surgery_date(self, temp_db: DatabaseManager) -> None:
        """Test setting user surgery date."""
        user_id = "123456@s.whatsapp.net"
        surgery_date = "2026-01-15"

        temp_db.set_surgery_date(user_id, surgery_date, "Dr. Smith", "ACL Reconstruction")

        config = temp_db.get_user_config(user_id)
        assert config is not None
        assert config.user_id == user_id
        assert config.surgery_date == surgery_date
        assert config.surgeon_name == "Dr. Smith"
        assert config.surgery_type == "ACL Reconstruction"

    def test_log_daily_metrics(self, temp_db: DatabaseManager) -> None:
        """Test logging daily metrics."""
        user_id = "123456@s.whatsapp.net"

        result = temp_db.log_daily_metrics(
            user_id=user_id,
            pain_level=4,
            swelling_status="same",
            rom_extension=5,
            rom_flexion=110,
            adherence=True,
            notes="Feeling good today",
        )

        assert result.success is True
        assert "Metrics logged successfully" in result.message

        # Verify data was stored
        metrics = temp_db.get_latest_metrics(user_id)
        assert metrics is not None
        assert metrics.pain_level == 4
        assert metrics.swelling_status == "same"
        assert metrics.rom_extension == 5
        assert metrics.rom_flexion == 110
        assert metrics.adherence is True
        assert metrics.notes == "Feeling good today"

    def test_upsert_metrics(self, temp_db: DatabaseManager) -> None:
        """Test that logging metrics for the same day updates existing record."""
        user_id = "123456@s.whatsapp.net"

        # First log
        temp_db.log_daily_metrics(
            user_id=user_id,
            pain_level=4,
            swelling_status="same",
            rom_extension=5,
            rom_flexion=110,
            adherence=True,
        )

        # Second log (should update)
        temp_db.log_daily_metrics(
            user_id=user_id,
            pain_level=3,
            swelling_status="better",
            rom_extension=3,
            rom_flexion=115,
            adherence=True,
        )

        # Should only have one record for today
        history = temp_db.get_metrics_history(user_id, 7)
        assert len(history) == 1
        assert history[0].pain_level == 3  # Updated value

    def test_get_metrics_history(self, temp_db: DatabaseManager) -> None:
        """Test getting metrics history."""
        user_id = "123456@s.whatsapp.net"

        # Log a metric
        temp_db.log_daily_metrics(
            user_id=user_id,
            pain_level=4,
            swelling_status="same",
            rom_extension=5,
            rom_flexion=110,
            adherence=True,
        )

        history = temp_db.get_metrics_history(user_id, 7)
        assert len(history) == 1
        assert history[0].user_id == user_id


class TestACLRehabTools:
    """Tests for ACLRehabTools class."""

    def test_get_recovery_phase_no_surgery_date(self, tools: ACLRehabTools) -> None:
        """Test get_recovery_phase when surgery date is not configured."""
        result = tools.get_recovery_phase("unknown_user")

        assert result.error is True
        assert "Surgery date not configured" in (result.message or "")

    def test_get_recovery_phase_phase1(self, tools: ACLRehabTools, temp_db: DatabaseManager) -> None:
        """Test get_recovery_phase returns Phase 1 for first 2 weeks."""
        user_id = "123456@s.whatsapp.net"
        # Surgery date 1 week ago
        surgery_date = (date.today() - timedelta(days=7)).isoformat()
        temp_db.set_surgery_date(user_id, surgery_date)

        result = tools.get_recovery_phase(user_id)

        assert result.error is False
        assert result.phase == "Phase 1"
        assert result.phase_name == "Protection & Initial Recovery"
        assert result.weeks_post_op == 1
        assert result.recommended_exercises is not None
        assert len(result.recommended_exercises) > 0

    def test_get_recovery_phase_phase2(self, tools: ACLRehabTools, temp_db: DatabaseManager) -> None:
        """Test get_recovery_phase returns Phase 2 for weeks 2-6."""
        user_id = "123456@s.whatsapp.net"
        # Surgery date 4 weeks ago
        surgery_date = (date.today() - timedelta(days=28)).isoformat()
        temp_db.set_surgery_date(user_id, surgery_date)

        result = tools.get_recovery_phase(user_id)

        assert result.error is False
        assert result.phase == "Phase 2"
        assert result.phase_name == "Early Strengthening"
        assert result.weeks_post_op == 4

    def test_get_recovery_phase_phase3(self, tools: ACLRehabTools, temp_db: DatabaseManager) -> None:
        """Test get_recovery_phase returns Phase 3 for weeks 6-12."""
        user_id = "123456@s.whatsapp.net"
        # Surgery date 8 weeks ago
        surgery_date = (date.today() - timedelta(days=56)).isoformat()
        temp_db.set_surgery_date(user_id, surgery_date)

        result = tools.get_recovery_phase(user_id)

        assert result.error is False
        assert result.phase == "Phase 3"
        assert result.phase_name == "Progressive Loading"
        assert result.weeks_post_op == 8

    def test_get_recovery_phase_phase4(self, tools: ACLRehabTools, temp_db: DatabaseManager) -> None:
        """Test get_recovery_phase returns Phase 4 for 12+ weeks."""
        user_id = "123456@s.whatsapp.net"
        # Surgery date 16 weeks ago
        surgery_date = (date.today() - timedelta(days=112)).isoformat()
        temp_db.set_surgery_date(user_id, surgery_date)

        result = tools.get_recovery_phase(user_id)

        assert result.error is False
        assert result.phase == "Phase 4"
        assert result.phase_name == "Return to Sport Preparation"
        assert result.weeks_post_op == 16

    def test_log_daily_metrics_tool(self, tools: ACLRehabTools) -> None:
        """Test log_daily_metrics tool execution."""
        user_id = "123456@s.whatsapp.net"

        result = tools.log_daily_metrics(
            user_id=user_id,
            pain_level=4,
            swelling_status="same",
            rom_extension=5,
            rom_flexion=110,
            adherence=True,
        )

        assert result["success"] is True
        assert "Metrics logged successfully" in result["message"]

    def test_get_tool_definitions(self, tools: ACLRehabTools) -> None:
        """Test tool definitions are properly formatted."""
        definitions = tools.get_tool_definitions()

        assert len(definitions) >= 3

        tool_names = [d["function"]["name"] for d in definitions]
        assert "log_daily_metrics" in tool_names
        assert "get_recovery_phase" in tool_names

    @pytest.mark.asyncio
    async def test_execute_tool_log_metrics(self, tools: ACLRehabTools) -> None:
        """Test execute_tool for log_daily_metrics."""
        user_id = "123456@s.whatsapp.net"

        result = await tools.execute_tool(
            "log_daily_metrics",
            user_id,
            {
                "pain_level": 4,
                "swelling_status": "same",
                "rom_extension": 5,
                "rom_flexion": 110,
                "adherence": True,
            },
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_tool_unknown(self, tools: ACLRehabTools) -> None:
        """Test execute_tool for unknown tool."""
        result = await tools.execute_tool("unknown_tool", "user", {})

        assert result["error"] is True
        assert "Unknown tool" in result["message"]


def test_set_reminder_persists_is_active(tools: ACLRehabTools, temp_db: DatabaseManager, monkeypatch) -> None:
    """Integration test: set_reminder schedules job and persists is_active=1.

    Uses monkeypatch to safely replace the module-level scheduler and ensure teardown.
    """
    from sqlalchemy import text

    class DummyScheduler:
        def add_job(self, func, trigger, *args, **kwargs):
            # Accept arbitrary kwargs to mirror APScheduler signature; capture id if provided
            self.last_job_id = kwargs.get("id")

    # Install dummy scheduler via monkeypatch to avoid test pollution
    monkeypatch.setattr("app.scheduler.scheduler", DummyScheduler())

    user_id = "testuser@whatsapp"
    result = tools.set_reminder(user_id=user_id, task="Drink Water", schedule_type="interval", time_value="1")

    assert result.get("success") is True
    reminder_id = result.get("reminder_id")
    assert reminder_id is not None

    # Verify DB row persisted with is_active = 1. Query by user_id to avoid tight coupling
    with temp_db.engine.connect() as conn:
        row = conn.execute(
            text("SELECT job_id, is_active FROM reminders WHERE user_id = :uid ORDER BY id DESC LIMIT 1"),
            {"uid": user_id},
        ).fetchone()

    assert row is not None
    # SQLite may return 0/1 or True/False; normalize to int
    assert int(row[1]) == 1
