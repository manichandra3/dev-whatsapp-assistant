import sqlite3
import logging

logging.basicConfig(level=logging.INFO)

def migrate_db(db_path="./data/acl_rehab.db"):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Check if user_config has new columns
    cur.execute("PRAGMA table_info(user_config)")
    columns = [row[1] for row in cur.fetchall()]
    
    if "gamification_opt_in" not in columns:
        logging.info("Adding gamification_opt_in to user_config")
        cur.execute("ALTER TABLE user_config ADD COLUMN gamification_opt_in BOOLEAN DEFAULT 0")
        
    if "notify_badges" not in columns:
        logging.info("Adding notify_badges to user_config")
        cur.execute("ALTER TABLE user_config ADD COLUMN notify_badges BOOLEAN DEFAULT 1")
        
    if "timezone" not in columns:
        logging.info("Adding timezone to user_config")
        cur.execute("ALTER TABLE user_config ADD COLUMN timezone TEXT DEFAULT 'UTC'")
        
    if "goals" not in columns:
        logging.info("Adding goals to user_config")
        cur.execute("ALTER TABLE user_config ADD COLUMN goals TEXT")
        
    # Create onboarding_sessions table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS onboarding_sessions (
        user_id TEXT PRIMARY KEY,
        current_step INTEGER NOT NULL DEFAULT 1,
        surgery_date TEXT,
        baseline_pain INTEGER,
        goal TEXT,
        timezone TEXT,
        gamification_opt_in BOOLEAN,
        notification_freq TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Create adherence_streaks table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS adherence_streaks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL UNIQUE,
        current_streak_days INTEGER DEFAULT 0,
        longest_streak_days INTEGER DEFAULT 0,
        last_streak_date DATE,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Create badges table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS badges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        icon_path TEXT,
        criteria TEXT
    )
    """)
    
    # Create user_badges table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_badges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        badge_id INTEGER NOT NULL,
        awarded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(badge_id) REFERENCES badges(id)
    )
    """)

    # Populate default badges
    default_badges = [
        ("first_log", "First Check-in", "Completed your first daily check-in", None, '{"type": "first_log"}'),
        ("streak_3", "3-Day Streak", "Logged metrics for 3 consecutive days", None, '{"type": "streak", "days": 3}'),
        ("streak_7", "1-Week Streak", "Logged metrics for 7 consecutive days", None, '{"type": "streak", "days": 7}'),
        ("streak_14", "2-Week Streak", "Logged metrics for 14 consecutive days", None, '{"type": "streak", "days": 14}'),
        ("consistency_month", "Consistency Medal", "Logged 20 or more days in a 30-day window", None, '{"type": "consistency", "days": 20, "window": 30}')
    ]
    
    for badge in default_badges:
        cur.execute("INSERT OR IGNORE INTO badges (key, title, description, icon_path, criteria) VALUES (?, ?, ?, ?, ?)", badge)
        
    conn.commit()
    conn.close()
    logging.info("Migration complete.")

if __name__ == "__main__":
    migrate_db()
