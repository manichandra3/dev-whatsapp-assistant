"""
Database and Tools Test Suite

Tests for database operations and tool execution.
"""

import os
import tempfile
from datetime import date, datetime, timedelta

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

        assert result.success is False
        assert result.error is True
        assert "Surgery date not configured" in (result.message or "")

    def test_get_recovery_phase_phase1(self, tools: ACLRehabTools, temp_db: DatabaseManager) -> None:
        """Test get_recovery_phase returns Phase 1 for first 2 weeks."""
        user_id = "123456@s.whatsapp.net"
        # Surgery date 1 week ago
        surgery_date = (date.today() - timedelta(days=7)).isoformat()
        temp_db.set_surgery_date(user_id, surgery_date)

        result = tools.get_recovery_phase(user_id)

        assert result.success is True
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

        assert result.success is True
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

        assert result.success is True
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

        assert result.success is True
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

        assert len(definitions) == 2

        # Check log_daily_metrics
        log_tool = definitions[0]
        assert log_tool["type"] == "function"
        assert log_tool["function"]["name"] == "log_daily_metrics"
        assert "parameters" in log_tool["function"]

        # Check get_recovery_phase
        phase_tool = definitions[1]
        assert phase_tool["type"] == "function"
        assert phase_tool["function"]["name"] == "get_recovery_phase"

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
