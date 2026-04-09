"""
Database Manager - SQLite Storage for ACL Rehab Metrics

Handles all database operations for storing and retrieving patient metrics.
Uses SQLAlchemy Core for direct SQL execution while maintaining compatibility
with the existing Node.js database schema.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    select,
    text,
)
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


@dataclass
class DailyMetrics:
    """Daily metrics record from database."""

    id: int
    user_id: str
    date: str
    timestamp: str
    pain_level: int
    swelling_status: str
    rom_extension: int
    rom_flexion: int
    adherence: bool
    notes: str | None


@dataclass
class UserConfig:
    """User configuration record from database."""

    user_id: str
    surgery_date: str
    surgeon_name: str | None
    surgery_type: str | None
    created_at: str
    updated_at: str


@dataclass
class MetricsLogResult:
    """Result of logging daily metrics."""

    success: bool
    message: str
    data: dict[str, Any] | None = None


@dataclass
class MetricsTrends:
    """Calculated metrics trends."""

    pain_trend: int
    rom_extension_trend: int
    rom_flexion_trend: int
    swelling_trend: int
    adherence_rate: float


class DatabaseManager:
    """
    Database manager for ACL Rehab metrics.

    Maintains compatibility with the existing Node.js better-sqlite3 schema.
    """

    def __init__(self, db_path: str = "./data/acl_rehab.db") -> None:
        self.db_path = db_path
        self.engine: Engine | None = None
        self.metadata = MetaData()
        self._define_tables()
        self._init()

    def _define_tables(self) -> None:
        """Define table schemas matching the Node.js implementation."""
        # Daily metrics table
        self.daily_metrics = Table(
            "daily_metrics",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("user_id", Text, nullable=False),
            Column(
                "date", Text, nullable=False, server_default=text("DATE('now')")
            ),
            Column(
                "timestamp", DateTime, nullable=False, server_default=text("DATETIME('now')")
            ),
            Column("pain_level", Integer, nullable=False),
            Column("swelling_status", Text, nullable=False),
            Column("rom_extension", Integer, nullable=False),
            Column("rom_flexion", Integer, nullable=False),
            Column("adherence", Boolean, nullable=False),
            Column("notes", Text),
            CheckConstraint("pain_level >= 0 AND pain_level <= 10"),
            CheckConstraint("swelling_status IN ('worse', 'same', 'better')"),
            UniqueConstraint("user_id", "date"),
        )

        # Recovery milestones table
        self.recovery_milestones = Table(
            "recovery_milestones",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("user_id", Text, nullable=False),
            Column("milestone_name", Text, nullable=False),
            Column("achieved_date", Text, nullable=False),
            Column("weeks_post_op", Integer, nullable=False),
            Column("notes", Text),
        )

        # User configuration table
        self.user_config = Table(
            "user_config",
            self.metadata,
            Column("user_id", Text, primary_key=True),
            Column("surgery_date", Text, nullable=False),
            Column("surgeon_name", Text),
            Column("surgery_type", Text),
            Column(
                "created_at", DateTime, nullable=False, server_default=text("DATETIME('now')")
            ),
            Column(
                "updated_at", DateTime, nullable=False, server_default=text("DATETIME('now')")
            ),
        )

    def _init(self) -> None:
        """Initialize database connection and create tables."""
        # Ensure data directory exists
        data_dir = Path(self.db_path).parent
        data_dir.mkdir(parents=True, exist_ok=True)

        # Create engine with WAL mode for better performance
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )

        # Set WAL mode
        with self.engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode = WAL"))
            conn.commit()

        # Create tables
        self.metadata.create_all(self.engine)

        # Create indexes
        self._create_indexes()

        logger.info(f"[DATABASE] Connected to {self.db_path}")

    def _create_indexes(self) -> None:
        """Create indexes for better query performance."""
        with self.engine.connect() as conn:
            # Index on user_id and date for daily_metrics
            conn.execute(
                text(
                    """
                CREATE INDEX IF NOT EXISTS idx_daily_metrics_user_date 
                ON daily_metrics(user_id, date DESC)
                """
                )
            )
            # Index on timestamp for daily_metrics
            conn.execute(
                text(
                    """
                CREATE INDEX IF NOT EXISTS idx_daily_metrics_timestamp 
                ON daily_metrics(timestamp DESC)
                """
                )
            )
            conn.commit()
        logger.info("[DATABASE] Tables initialized")

    def log_daily_metrics(
        self,
        user_id: str,
        pain_level: int,
        swelling_status: str,
        rom_extension: int,
        rom_flexion: int,
        adherence: bool,
        notes: str | None = None,
    ) -> MetricsLogResult:
        """
        Log daily metrics for a user.

        Uses upsert semantics - if metrics exist for today, they are updated.
        """
        try:
            with self.engine.connect() as conn:
                # Use INSERT OR REPLACE for upsert behavior matching Node.js
                conn.execute(
                    text(
                        """
                    INSERT INTO daily_metrics 
                        (user_id, pain_level, swelling_status, rom_extension, rom_flexion, adherence, notes)
                    VALUES 
                        (:user_id, :pain_level, :swelling_status, :rom_extension, :rom_flexion, :adherence, :notes)
                    ON CONFLICT(user_id, date) 
                    DO UPDATE SET 
                        pain_level = excluded.pain_level,
                        swelling_status = excluded.swelling_status,
                        rom_extension = excluded.rom_extension,
                        rom_flexion = excluded.rom_flexion,
                        adherence = excluded.adherence,
                        notes = excluded.notes,
                        timestamp = DATETIME('now')
                    """
                    ),
                    {
                        "user_id": user_id,
                        "pain_level": pain_level,
                        "swelling_status": swelling_status,
                        "rom_extension": rom_extension,
                        "rom_flexion": rom_flexion,
                        "adherence": 1 if adherence else 0,
                        "notes": notes,
                    },
                )
                conn.commit()

            today = date.today().isoformat()
            adherence_str = "Completed ✓" if adherence else "Not done ✗"

            logger.info(f"[DATABASE] Logged metrics for user {user_id}")

            return MetricsLogResult(
                success=True,
                message=(
                    f"✅ Metrics logged successfully!\n\n"
                    f"📊 Today's Check-in:\n"
                    f"• Pain: {pain_level}/10\n"
                    f"• Swelling: {swelling_status}\n"
                    f"• ROM: {rom_extension}° extension, {rom_flexion}° flexion\n"
                    f"• Exercises: {adherence_str}"
                ),
                data={
                    "userId": user_id,
                    "date": today,
                    "painLevel": pain_level,
                    "swellingStatus": swelling_status,
                    "romExtension": rom_extension,
                    "romFlexion": rom_flexion,
                    "adherence": adherence,
                },
            )

        except Exception as e:
            logger.error(f"[DATABASE] Error logging metrics: {e}")
            return MetricsLogResult(
                success=False,
                message=f"❌ Error logging metrics: {e}",
            )

    def get_latest_metrics(self, user_id: str) -> DailyMetrics | None:
        """Get latest metrics for a user."""
        with self.engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT * FROM daily_metrics
                WHERE user_id = :user_id
                ORDER BY date DESC
                LIMIT 1
                """
                ),
                {"user_id": user_id},
            ).fetchone()

            if result:
                return DailyMetrics(
                    id=result[0],
                    user_id=result[1],
                    date=result[2],
                    timestamp=str(result[3]),
                    pain_level=result[4],
                    swelling_status=result[5],
                    rom_extension=result[6],
                    rom_flexion=result[7],
                    adherence=bool(result[8]),
                    notes=result[9],
                )
            return None

    def get_metrics_history(self, user_id: str, days: int = 7) -> list[DailyMetrics]:
        """Get metrics history for a user (last N days)."""
        with self.engine.connect() as conn:
            results = conn.execute(
                text(
                    """
                SELECT * FROM daily_metrics
                WHERE user_id = :user_id
                ORDER BY date DESC
                LIMIT :days
                """
                ),
                {"user_id": user_id, "days": days},
            ).fetchall()

            return [
                DailyMetrics(
                    id=row[0],
                    user_id=row[1],
                    date=row[2],
                    timestamp=str(row[3]),
                    pain_level=row[4],
                    swelling_status=row[5],
                    rom_extension=row[6],
                    rom_flexion=row[7],
                    adherence=bool(row[8]),
                    notes=row[9],
                )
                for row in results
            ]

    def get_user_config(self, user_id: str) -> UserConfig | None:
        """Get or create user configuration."""
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT * FROM user_config WHERE user_id = :user_id"),
                {"user_id": user_id},
            ).fetchone()

            if result:
                return UserConfig(
                    user_id=result[0],
                    surgery_date=result[1],
                    surgeon_name=result[2],
                    surgery_type=result[3],
                    created_at=str(result[4]),
                    updated_at=str(result[5]),
                )
            return None

    def set_surgery_date(
        self,
        user_id: str,
        surgery_date: str,
        surgeon_name: str | None = None,
        surgery_type: str = "ACL Reconstruction",
    ) -> None:
        """Set user surgery date."""
        with self.engine.connect() as conn:
            conn.execute(
                text(
                    """
                INSERT INTO user_config (user_id, surgery_date, surgeon_name, surgery_type)
                VALUES (:user_id, :surgery_date, :surgeon_name, :surgery_type)
                ON CONFLICT(user_id)
                DO UPDATE SET
                    surgery_date = excluded.surgery_date,
                    surgeon_name = excluded.surgeon_name,
                    surgery_type = excluded.surgery_type,
                    updated_at = DATETIME('now')
                """
                ),
                {
                    "user_id": user_id,
                    "surgery_date": surgery_date,
                    "surgeon_name": surgeon_name,
                    "surgery_type": surgery_type,
                },
            )
            conn.commit()
        logger.info(f"[DATABASE] Set surgery date for {user_id}: {surgery_date}")

    def get_metrics_trends(self, user_id: str, days: int = 7) -> MetricsTrends | None:
        """Calculate metrics trends."""
        history = self.get_metrics_history(user_id, days)

        if len(history) < 2:
            return None

        latest = history[0]
        previous = history[1]

        swelling_trend = 0
        if latest.swelling_status == "better":
            swelling_trend = 1
        elif latest.swelling_status == "worse":
            swelling_trend = -1

        adherence_count = sum(1 for m in history if m.adherence)
        adherence_rate = adherence_count / len(history)

        return MetricsTrends(
            pain_trend=latest.pain_level - previous.pain_level,
            rom_extension_trend=latest.rom_extension - previous.rom_extension,
            rom_flexion_trend=latest.rom_flexion - previous.rom_flexion,
            swelling_trend=swelling_trend,
            adherence_rate=adherence_rate,
        )

    def close(self) -> None:
        """Close database connection."""
        if self.engine:
            self.engine.dispose()
            logger.info("[DATABASE] Connection closed")
