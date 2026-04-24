"""
Database Test Suite
"""

import os
import tempfile
from datetime import UTC, datetime, timedelta
import pytest

from app.database import DatabaseManager

@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = DatabaseManager(db_path)
        yield db
        db.close()

class TestDatabaseManager:
    def test_initialization(self, temp_db: DatabaseManager) -> None:
        """Test database initialization creates tables."""
        user = temp_db.get_or_create_user("test_user")
        assert user.user_id == "test_user"
        
    def test_save_and_get_messages(self, temp_db: DatabaseManager) -> None:
        """Test saving and retrieving messages."""
        user_id = "test_user"
        temp_db.save_message(user_id, "user", "Hello")
        temp_db.save_message(user_id, "assistant", "Hi there")
        
        messages = temp_db.get_recent_messages(user_id)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Hi there"

    def test_due_scheduled_tasks_lifecycle(self, temp_db: DatabaseManager) -> None:
        user_id = "test_user"
        due_at = datetime.now(UTC) - timedelta(minutes=1)

        temp_db.save_scheduled_task(
            user_id=user_id,
            description="drink water",
            schedule_details="Time: now, Frequency: once",
            due_at=due_at,
            frequency="once",
        )

        due_tasks = temp_db.get_due_scheduled_tasks(limit=10)
        assert len(due_tasks) == 1
        assert due_tasks[0].user_id == user_id
        assert due_tasks[0].task_description == "drink water"
        assert due_tasks[0].status == "processing"

        temp_db.mark_scheduled_task_delivered(due_tasks[0].id)
        due_again = temp_db.get_due_scheduled_tasks(limit=10)
        assert due_again == []
