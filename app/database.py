"""
Database Manager - SQLite Storage for Developer WhatsApp Assistant

Handles all database operations for stateful memory and intent logging.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
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
            conn.commit()

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
                    ORDER BY timestamp DESC LIMIT :limit
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

    def close(self) -> None:
        """Close database connection."""
        if self.engine:
            self.engine.dispose()
            logger.info("[DATABASE] Connection closed")
