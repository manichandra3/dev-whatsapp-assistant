"""
Database Manager - SQLite Storage for Developer WhatsApp Assistant

Handles all database operations for stateful memory and intent logging.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    text,
)
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


@dataclass
class User:
    """User record from database."""
    user_id: str
    created_at: str
    preferences: dict[str, Any]


@dataclass
class Message:
    """Chat message record."""
    id: int
    user_id: str
    role: str
    content: str
    timestamp: str


@dataclass
class ScheduledTask:
    """Scheduled task record."""

    id: int
    user_id: str
    task_description: str
    schedule_details: str
    status: str
    due_at: str
    frequency: str


class DatabaseManager:
    """Database manager for the Developer WhatsApp Assistant."""

    def __init__(self, db_path: str = "./data/dev_assistant.db") -> None:
        self.db_path = db_path
        self.engine: Engine | None = None
        self.metadata = MetaData()
        self._define_tables()
        self._init()

    def _define_tables(self) -> None:
        """Define table schemas."""
        
        self.users = Table(
            "users",
            self.metadata,
            Column("user_id", Text, primary_key=True),
            Column("created_at", DateTime, nullable=False, server_default=text("DATETIME('now')")),
            Column("preferences", Text, nullable=False, server_default="{}"),
        )

        self.messages = Table(
            "messages",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("user_id", Text, nullable=False),
            Column("role", Text, nullable=False),
            Column("content", Text, nullable=False),
            Column("timestamp", DateTime, nullable=False, server_default=text("DATETIME('now')")),
        )

        self.intent_logs = Table(
            "intent_logs",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("user_id", Text, nullable=False),
            Column("original_message", Text, nullable=False),
            Column("intent", Text, nullable=False),
            Column("topic", Text, nullable=False),
            Column("metadata_json", Text, nullable=False),
            Column("timestamp", DateTime, nullable=False, server_default=text("DATETIME('now')")),
        )

        self.scheduled_tasks = Table(
            "scheduled_tasks",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("user_id", Text, nullable=False),
            Column("task_description", Text, nullable=False),
            Column("schedule_details", Text, nullable=False),
            Column("status", Text, nullable=False, server_default="pending"),
            Column("due_at", DateTime, nullable=True),
            Column("frequency", Text, nullable=False, server_default="once"),
            Column("delivered_at", DateTime, nullable=True),
            Column("attempt_count", Integer, nullable=False, server_default="0"),
            Column("last_attempt_at", DateTime, nullable=True),
            Column("created_at", DateTime, nullable=False, server_default=text("DATETIME('now')")),
        )

        self.expense_logs = Table(
            "expense_logs",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("user_id", Text, nullable=False),
            Column("amount", Text, nullable=False),
            Column("currency", Text, nullable=False),
            Column("category", Text, nullable=False),
            Column("note", Text, nullable=True),
            Column("source_message", Text, nullable=False),
            Column("timestamp", DateTime, nullable=False, server_default=text("DATETIME('now')")),
        )

        self.code_runs = Table(
            "code_runs",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("user_id", Text, nullable=False),
            Column("language", Text, nullable=False),
            Column("code_snippet", Text, nullable=False),
            Column("exit_status", Integer, nullable=False),
            Column("runtime_ms", Integer, nullable=False),
            Column("output", Text, nullable=True),
            Column("timestamp", DateTime, nullable=False, server_default=text("DATETIME('now')")),
        )

    def _init(self) -> None:
        """Initialize database connection and create tables."""
        data_dir = Path(self.db_path).parent
        data_dir.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )

        with self.engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode = WAL"))
            conn.commit()

        self.metadata.create_all(self.engine)

        with self.engine.connect() as conn:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_messages_user_time ON messages(user_id, timestamp DESC)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_intent_user_time ON intent_logs(user_id, timestamp DESC)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tasks_user_time ON scheduled_tasks(user_id, created_at DESC)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tasks_status_due ON scheduled_tasks(status, due_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_expenses_user_time ON expense_logs(user_id, timestamp DESC)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_runs_user_time ON code_runs(user_id, timestamp DESC)"))
            conn.commit()

        self._migrate_scheduled_tasks_table()

        logger.info(f"[DATABASE] Connected to {self.db_path}")

    def get_or_create_user(self, user_id: str) -> User:
        """Get existing user or create a new one."""
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT user_id, created_at, preferences FROM users WHERE user_id = :user_id"),
                {"user_id": user_id},
            ).fetchone()

            if result:
                return User(
                    user_id=result[0],
                    created_at=str(result[1]),
                    preferences=json.loads(result[2]) if result[2] else {},
                )
            
            # Create user
            conn.execute(
                text("INSERT INTO users (user_id, preferences) VALUES (:user_id, '{}')"),
                {"user_id": user_id},
            )
            conn.commit()
            
            # Fetch newly created
            result = conn.execute(
                text("SELECT user_id, created_at, preferences FROM users WHERE user_id = :user_id"),
                {"user_id": user_id},
            ).fetchone()
            
            return User(
                user_id=result[0],
                created_at=str(result[1]),
                preferences=json.loads(result[2]),
            )

    def save_message(self, user_id: str, role: str, content: str) -> None:
        """Save a chat message to history."""
        with self.engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO messages (user_id, role, content) VALUES (:user_id, :role, :content)"
                ),
                {"user_id": user_id, "role": role, "content": content},
            )
            conn.commit()

    def get_recent_messages(self, user_id: str, limit: int = 10) -> list[dict[str, str]]:
        """Fetch the most recent conversation history for a user, oldest first."""
        with self.engine.connect() as conn:
            results = conn.execute(
                text(
                    """
                    SELECT role, content FROM messages 
                    WHERE user_id = :user_id 
                    ORDER BY id DESC LIMIT :limit
                    """
                ),
                {"user_id": user_id, "limit": limit},
            ).fetchall()

            # Reverse to get chronological order
            return [{"role": row[0], "content": row[1]} for row in reversed(results)]

    def log_intent(
        self,
        user_id: str,
        original_message: str,
        intent: str,
        topic: str,
        metadata: dict[str, Any],
    ) -> None:
        """Log a parsed intent."""
        with self.engine.connect() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO intent_logs (user_id, original_message, intent, topic, metadata_json)
                    VALUES (:user_id, :original_message, :intent, :topic, :metadata_json)
                    """
                ),
                {
                    "user_id": user_id,
                    "original_message": original_message,
                    "intent": intent,
                    "topic": topic,
                    "metadata_json": json.dumps(metadata),
                },
            )
            conn.commit()

    def _migrate_scheduled_tasks_table(self) -> None:
        """Apply additive migrations for scheduled_tasks columns."""
        with self.engine.connect() as conn:
            columns = conn.execute(text("PRAGMA table_info(scheduled_tasks)")).fetchall()
            existing_columns = {str(row[1]) for row in columns}

            if "due_at" not in existing_columns:
                conn.execute(text("ALTER TABLE scheduled_tasks ADD COLUMN due_at DATETIME"))
            if "frequency" not in existing_columns:
                conn.execute(
                    text("ALTER TABLE scheduled_tasks ADD COLUMN frequency TEXT NOT NULL DEFAULT 'once'")
                )
            if "delivered_at" not in existing_columns:
                conn.execute(text("ALTER TABLE scheduled_tasks ADD COLUMN delivered_at DATETIME"))
            if "attempt_count" not in existing_columns:
                conn.execute(text("ALTER TABLE scheduled_tasks ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0"))
            if "last_attempt_at" not in existing_columns:
                conn.execute(text("ALTER TABLE scheduled_tasks ADD COLUMN last_attempt_at DATETIME"))
            conn.commit()

    def save_scheduled_task(
        self,
        user_id: str,
        description: str,
        schedule_details: str,
        due_at: datetime,
        frequency: str = "once",
    ) -> None:
        """Save a scheduled task."""
        due_at_utc = due_at.astimezone(timezone.utc).replace(tzinfo=None)
        with self.engine.connect() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO scheduled_tasks (user_id, task_description, schedule_details, due_at, frequency)
                    VALUES (:user_id, :desc, :details, :due_at, :frequency)
                    """
                ),
                {
                    "user_id": user_id,
                    "desc": description,
                    "details": schedule_details,
                    "due_at": due_at_utc,
                    "frequency": frequency,
                },
            )
            conn.commit()

    def get_due_scheduled_tasks(self, limit: int = 50) -> list[ScheduledTask]:
        """Fetch due tasks and mark them as processing to avoid duplicate delivery."""
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, user_id, task_description, schedule_details, status, due_at, frequency
                    FROM scheduled_tasks
                    WHERE status = 'pending' AND due_at IS NOT NULL AND due_at <= :now_utc
                    ORDER BY due_at ASC
                    LIMIT :limit
                    """
                ),
                {"now_utc": now_utc, "limit": limit},
            ).fetchall()

            if not rows:
                return []

            task_ids = [int(row[0]) for row in rows]
            placeholders = ", ".join([f":id_{i}" for i in range(len(task_ids))])
            params: dict[str, Any] = {f"id_{i}": task_id for i, task_id in enumerate(task_ids)}
            conn.execute(
                text(
                    f"UPDATE scheduled_tasks SET status = 'processing' WHERE id IN ({placeholders}) AND status = 'pending'"
                ),
                params,
            )

        return [
            ScheduledTask(
                id=int(row[0]),
                user_id=str(row[1]),
                task_description=str(row[2]),
                schedule_details=str(row[3]),
                status="processing",
                due_at=str(row[5]),
                frequency=str(row[6] or "once"),
            )
            for row in rows
        ]

    def mark_scheduled_task_delivered(self, task_id: int) -> None:
        """Mark a scheduled task as delivered."""
        with self.engine.connect() as conn:
            conn.execute(
                text(
                    """
                    UPDATE scheduled_tasks
                    SET status = 'delivered', delivered_at = DATETIME('now')
                    WHERE id = :task_id
                    """
                ),
                {"task_id": task_id},
            )
            conn.commit()

    def mark_scheduled_task_pending(self, task_id: int) -> None:
        """Requeue a scheduled task when delivery fails."""
        with self.engine.connect() as conn:
            conn.execute(
                text(
                    """
                    UPDATE scheduled_tasks
                    SET status = 'pending'
                    WHERE id = :task_id
                    """
                ),
                {"task_id": task_id},
            )
            conn.commit()

    def get_user_tasks(self, user_id: str, status: str = "pending") -> list[ScheduledTask]:
        """Get all tasks for a user with given status."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, user_id, task_description, schedule_details, status, due_at, frequency
                    FROM scheduled_tasks
                    WHERE user_id = :user_id AND status = :status
                    ORDER BY due_at ASC
                    """
                ),
                {"user_id": user_id, "status": status},
            ).fetchall()

            return [
                ScheduledTask(
                    id=int(row[0]),
                    user_id=str(row[1]),
                    task_description=str(row[2]),
                    schedule_details=str(row[3]),
                    status=str(row[4]),
                    due_at=str(row[5]),
                    frequency=str(row[6] or "once"),
                )
                for row in rows
            ]

    def cancel_scheduled_task(self, task_id: int, user_id: str) -> bool:
        """Cancel a scheduled task. Returns True if cancelled, False if not found."""
        with self.engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE scheduled_tasks
                    SET status = 'cancelled'
                    WHERE id = :task_id AND user_id = :user_id AND status = 'pending'
                    """
                ),
                {"task_id": task_id, "user_id": user_id},
            )
            conn.commit()
            return result.rowcount > 0

    def mark_scheduled_task_failed(self, task_id: int) -> None:
        """Mark a task as failed (dead-letter)."""
        with self.engine.connect() as conn:
            conn.execute(
                text(
                    """
                    UPDATE scheduled_tasks
                    SET status = 'failed'
                    WHERE id = :task_id
                    """
                ),
                {"task_id": task_id},
            )
            conn.commit()

    def is_task_already_delivered(self, task_id: int) -> bool:
        """Check if a task has already been delivered (idempotency)."""
        with self.engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT status FROM scheduled_tasks WHERE id = :task_id
                    """
                ),
                {"task_id": task_id},
            ).fetchone()
            return result is not None and result[0] == "delivered"

    def increment_task_attempt(self, task_id: int) -> None:
        """Increment the attempt count for a task."""
        with self.engine.connect() as conn:
            conn.execute(
                text(
                    """
                    UPDATE scheduled_tasks
                    SET attempt_count = attempt_count + 1,
                        last_attempt_at = DATETIME('now')
                    WHERE id = :task_id
                    """
                ),
                {"task_id": task_id},
            )
            conn.commit()

    def get_task_attempt_count(self, task_id: int) -> int:
        """Get the current attempt count for a task."""
        with self.engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT attempt_count FROM scheduled_tasks WHERE id = :task_id
                    """
                ),
                {"task_id": task_id},
            ).fetchone()
            return int(result[0]) if result else 0

    def requeue_scheduled_task_with_delay(self, task_id: int, delay_minutes: int) -> None:
        """Requeue a task with a delay (update due_at and set status back to pending)."""
        with self.engine.connect() as conn:
            conn.execute(
                text(
                    """
                    UPDATE scheduled_tasks
                    SET status = 'pending',
                        due_at = DATETIME(due_at, '+' || :delay || ' minutes')
                    WHERE id = :task_id
                    """
                ),
                {"task_id": task_id, "delay": delay_minutes},
            )
            conn.commit()

    def log_expense(self, user_id: str, amount: str, currency: str, category: str, note: str, source: str) -> None:
        """Log an expense."""
        with self.engine.connect() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO expense_logs (user_id, amount, currency, category, note, source_message)
                    VALUES (:user_id, :amount, :currency, :category, :note, :source)
                    """
                ),
                {
                    "user_id": user_id,
                    "amount": amount,
                    "currency": currency,
                    "category": category,
                    "note": note,
                    "source": source,
                },
            )
            conn.commit()

    def log_code_run(self, user_id: str, language: str, code: str, exit_status: int, runtime_ms: int, output: str) -> None:
        """Log a code execution run."""
        with self.engine.connect() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO code_runs (user_id, language, code_snippet, exit_status, runtime_ms, output)
                    VALUES (:user_id, :language, :code, :exit_status, :runtime_ms, :output)
                    """
                ),
                {
                    "user_id": user_id,
                    "language": language,
                    "code": code,
                    "exit_status": exit_status,
                    "runtime_ms": runtime_ms,
                    "output": output,
                },
            )
            conn.commit()

    def close(self) -> None:
        """Close database connection."""
        if self.engine:
            self.engine.dispose()
            logger.info("[DATABASE] Connection closed")
