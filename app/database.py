"""
Database Manager - SQLite Storage for ACL Rehab Metrics

Handles all database operations for storing and retrieving patient metrics.
Uses SQLAlchemy Core for direct SQL execution while maintaining compatibility
with the existing Node.js database schema.
"""

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
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
    gamification_opt_in: bool
    notify_badges: bool
    timezone: str
    goals: str | None
    image_opt_in: bool | None = None
    image_auto_confirm: bool | None = None
    whatsapp_reminder_opt_in: bool = False
    opt_in_timestamp: str | None = None
    last_user_message_at: str | None = None
    messages_sent_today: int = 0
    last_sent_date: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


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
            Column("gamification_opt_in", Boolean, default=False),
            Column("notify_badges", Boolean, default=True),
            Column("timezone", Text, default="UTC"),
            Column("goals", Text),
            Column("image_opt_in", Boolean, default=False),
            Column("image_auto_confirm", Boolean, default=False),
            Column("whatsapp_reminder_opt_in", Boolean, default=False),
            Column("opt_in_timestamp", DateTime),
            Column("last_user_message_at", DateTime),
            Column("messages_sent_today", Integer, default=0),
            Column("last_sent_date", Text),
            Column(
                "created_at", DateTime, nullable=False, server_default=text("DATETIME('now')")
            ),
            Column(
                "updated_at", DateTime, nullable=False, server_default=text("DATETIME('now')")
            ),
        )

        # Onboarding sessions table
        self.onboarding_sessions = Table(
            "onboarding_sessions",
            self.metadata,
            Column("user_id", Text, primary_key=True),
            Column("current_step", Integer, nullable=False, default=1),
            Column("surgery_date", Text),
            Column("baseline_pain", Integer),
            Column("goal", Text),
            Column("timezone", Text),
            Column("gamification_opt_in", Boolean),
            Column("notification_freq", Text),
            Column(
                "updated_at", DateTime, nullable=False, server_default=text("DATETIME('now')")
            ),
        )

        # Adherence streaks table
        self.adherence_streaks = Table(
            "adherence_streaks",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("user_id", Text, nullable=False, unique=True),
            Column("current_streak_days", Integer, default=0),
            Column("longest_streak_days", Integer, default=0),
            Column("last_streak_date", Text), # DATE string
            Column(
                "updated_at", DateTime, nullable=False, server_default=text("DATETIME('now')")
            ),
        )

        # Badges table
        self.badges = Table(
            "badges",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("key", Text, unique=True, nullable=False),
            Column("title", Text, nullable=False),
            Column("description", Text, nullable=False),
            Column("icon_path", Text),
            Column("criteria", Text),
        )

        # User badges table
        self.user_badges = Table(
            "user_badges",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("user_id", Text, nullable=False),
            Column("badge_id", Integer, nullable=False),
            Column(
                "awarded_at", DateTime, nullable=False, server_default=text("DATETIME('now')")
            ),
        )

        # Reminders table
        self.reminders = Table(
            "reminders",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("user_id", Text, nullable=False),
            Column("job_id", Text, nullable=True),
            Column("reminder_type", Text, nullable=False), # water, medication, custom
            Column("interval_expression", Text, nullable=False),
            Column("is_active", Boolean, nullable=False, default=True),
            Column("created_at", DateTime, nullable=False, server_default=text("DATETIME('now')")),
            Column("source_media_id", Text),
            Column("med_name", Text),
            Column("dose", Text),
            Column("raw_text", Text),
        )

        # Adherence logs table
        self.adherence_logs = Table(
            "adherence_logs",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("user_id", Text, nullable=False),
            Column("reminder_type", Text, nullable=False),
            Column("action_time", DateTime, nullable=False, server_default=text("DATETIME('now')")),
            Column("status", Text, nullable=False), # completed, missed
        )

        self.media = Table(
            "media",
            self.metadata,
            Column("id", Text, primary_key=True),
            Column("user_id", Text, nullable=False),
            Column("path", Text, nullable=False),
            Column("mime", Text, nullable=False),
            Column("created_at", DateTime, nullable=False, server_default=text("DATETIME('now')")),
            Column("expires_at", DateTime, nullable=False),
            Column("sha256", Text, nullable=False),
        )

        self.prescription_parses = Table(
            "prescription_parses",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("user_id", Text, nullable=False),
            Column("media_id", Text, nullable=False),
            Column("raw_text", Text, nullable=False),
            Column("parsed_json", Text, nullable=False),
            Column("created_at", DateTime, nullable=False, server_default=text("DATETIME('now')")),
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
        
        # Run basic migrations for existing databases
        self._run_migrations()

        logger.info(f"[DATABASE] Connected to {self.db_path}")

    def _run_migrations(self) -> None:
        """Run basic ALTER TABLE migrations for existing databases."""
        with self.engine.connect() as conn:
            # Check user_config columns
            columns = conn.execute(text("PRAGMA table_info(user_config)")).fetchall()
            col_names = [c[1] for c in columns]
            
            if "image_opt_in" not in col_names:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN image_opt_in BOOLEAN DEFAULT 0"))
            if "image_auto_confirm" not in col_names:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN image_auto_confirm BOOLEAN DEFAULT 0"))
            if "whatsapp_reminder_opt_in" not in col_names:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN whatsapp_reminder_opt_in BOOLEAN DEFAULT 0"))
            if "opt_in_timestamp" not in col_names:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN opt_in_timestamp DATETIME"))
            if "last_user_message_at" not in col_names:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN last_user_message_at DATETIME"))
            if "messages_sent_today" not in col_names:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN messages_sent_today INTEGER DEFAULT 0"))
            if "last_sent_date" not in col_names:
                conn.execute(text("ALTER TABLE user_config ADD COLUMN last_sent_date TEXT"))

                
            # Check reminders columns
            columns = conn.execute(text("PRAGMA table_info(reminders)")).fetchall()
            col_names = [c[1] for c in columns]
            
            if "source_media_id" not in col_names:
                conn.execute(text("ALTER TABLE reminders ADD COLUMN source_media_id TEXT"))
            if "med_name" not in col_names:
                conn.execute(text("ALTER TABLE reminders ADD COLUMN med_name TEXT"))
            if "dose" not in col_names:
                conn.execute(text("ALTER TABLE reminders ADD COLUMN dose TEXT"))
            if "raw_text" not in col_names:
                conn.execute(text("ALTER TABLE reminders ADD COLUMN raw_text TEXT"))

            # Add last_stanza_id to reminders for reply matching
            if "last_stanza_id" not in col_names:
                conn.execute(text("ALTER TABLE reminders ADD COLUMN last_stanza_id TEXT"))

            # Check adherence_logs columns and add reminder_id and stanza_id if missing
            columns = conn.execute(text("PRAGMA table_info(adherence_logs)")).fetchall()
            if columns:
                al_col_names = [c[1] for c in columns]
                if "reminder_id" not in al_col_names:
                    conn.execute(text("ALTER TABLE adherence_logs ADD COLUMN reminder_id INTEGER"))
                if "stanza_id" not in al_col_names:
                    conn.execute(text("ALTER TABLE adherence_logs ADD COLUMN stanza_id TEXT"))

            conn.commit()

    def get_engine_or_raise(self) -> Engine:
        """Return the SQLAlchemy engine or raise a helpful error if not initialized."""
        if not getattr(self, "engine", None):
            raise RuntimeError("Database engine is not initialized. Ensure DatabaseManager._init() ran and the database path is correct.")
        return self.engine

    def _create_indexes(self) -> None:
        """Create indexes for better query performance."""
        with self.engine.connect() as conn:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_daily_metrics_user_date "
                    "ON daily_metrics(user_id, date DESC)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_daily_metrics_timestamp "
                    "ON daily_metrics(timestamp DESC)"
                )
            )
            conn.commit()
        logger.info("[DATABASE] Tables initialized")

    @staticmethod
    def _row_to_metrics(row: Any) -> DailyMetrics:
        return DailyMetrics(
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

            return self._row_to_metrics(result) if result else None

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

            return [self._row_to_metrics(row) for row in results]

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
                    gamification_opt_in=bool(result[4]),
                    notify_badges=bool(result[5]),
                    timezone=result[6],
                    goals=result[7],
                    image_opt_in=bool(result[8]) if result[8] is not None else None,
                    image_auto_confirm=bool(result[9]) if result[9] is not None else None,
                    whatsapp_reminder_opt_in=bool(result[10]) if len(result) > 10 and result[10] is not None else False,
                    opt_in_timestamp=str(result[11]) if len(result) > 11 and result[11] is not None else None,
                    last_user_message_at=str(result[12]) if len(result) > 12 and result[12] is not None else None,
                    messages_sent_today=int(result[13]) if len(result) > 13 and result[13] is not None else 0,
                    last_sent_date=str(result[14]) if len(result) > 14 and result[14] is not None else None,
                    created_at=str(result[15]) if len(result) > 15 else str(result[10]),
                    updated_at=str(result[16]) if len(result) > 16 else str(result[11]),
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
                INSERT INTO user_config (user_id, surgery_date, surgeon_name, surgery_type, gamification_opt_in, notify_badges, timezone, image_opt_in, image_auto_confirm)
                VALUES (:user_id, :surgery_date, :surgeon_name, :surgery_type, 0, 1, 'UTC', 0, 0)
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

    def log_adherence(self, user_id: str, reminder_type: str, status: str = "completed") -> bool:
        """Log adherence to a reminder task."""
        try:
            with self.engine.connect() as conn:
                conn.execute(
                    text(
                        """
                    INSERT INTO adherence_logs (user_id, reminder_type, status)
                    VALUES (:user_id, :reminder_type, :status)
                    """
                    ),
                    {"user_id": user_id, "reminder_type": reminder_type, "status": status},
                )
                conn.commit()
            logger.info(f"[DATABASE] Logged adherence for {user_id}: {reminder_type} ({status})")
            return True
        except Exception as e:
            logger.error(f"[DATABASE] Error logging adherence: {e}")
            return False

    def close(self) -> None:
        """Close database connection."""
        if self.engine:
            self.engine.dispose()
            logger.info("[DATABASE] Connection closed")

    def update_last_message_time(self, user_id: str) -> None:
        with self.engine.connect() as conn:
            conn.execute(
                text("UPDATE user_config SET last_user_message_at = DATETIME('now') WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            conn.commit()
