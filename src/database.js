/**
 * Database Manager - SQLite Storage for ACL Rehab Metrics
 * 
 * Handles all database operations for storing and retrieving patient metrics
 */

import Database from 'better-sqlite3';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { mkdirSync, existsSync } from 'fs';

export class DatabaseManager {
  constructor(dbPath = './data/acl_rehab.db') {
    this.dbPath = dbPath;
    this.db = null;
    this.init();
  }

  init() {
    // Ensure data directory exists
    const dataDir = dirname(this.dbPath);
    if (!existsSync(dataDir)) {
      mkdirSync(dataDir, { recursive: true });
    }

    // Open database connection
    this.db = new Database(this.dbPath);
    this.db.pragma('journal_mode = WAL'); // Better performance

    // Create tables
    this.createTables();
    
    console.log(`[DATABASE] Connected to ${this.dbPath}`);
  }

  createTables() {
    // Daily metrics table
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS daily_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        date TEXT NOT NULL DEFAULT (DATE('now')),
        timestamp DATETIME NOT NULL DEFAULT (DATETIME('now')),
        pain_level INTEGER NOT NULL CHECK(pain_level >= 0 AND pain_level <= 10),
        swelling_status TEXT NOT NULL CHECK(swelling_status IN ('worse', 'same', 'better')),
        rom_extension INTEGER NOT NULL,
        rom_flexion INTEGER NOT NULL,
        adherence BOOLEAN NOT NULL,
        notes TEXT,
        UNIQUE(user_id, date)
      );
    `);

    // Recovery milestones table
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS recovery_milestones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        milestone_name TEXT NOT NULL,
        achieved_date DATE NOT NULL,
        weeks_post_op INTEGER NOT NULL,
        notes TEXT
      );
    `);

    // User configuration table (stores surgery date, etc.)
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS user_config (
        user_id TEXT PRIMARY KEY,
        surgery_date DATE NOT NULL,
        surgeon_name TEXT,
        surgery_type TEXT,
        created_at DATETIME NOT NULL DEFAULT (DATETIME('now')),
        updated_at DATETIME NOT NULL DEFAULT (DATETIME('now'))
      );
    `);

    // Create indexes for better query performance
    this.db.exec(`
      CREATE INDEX IF NOT EXISTS idx_daily_metrics_user_date 
      ON daily_metrics(user_id, date DESC);
      
      CREATE INDEX IF NOT EXISTS idx_daily_metrics_timestamp 
      ON daily_metrics(timestamp DESC);
    `);

    console.log('[DATABASE] Tables initialized');
  }

  /**
   * Log daily metrics for a user
   */
  logDailyMetrics({ userId, painLevel, swellingStatus, romExtension, romFlexion, adherence, notes = null }) {
    const stmt = this.db.prepare(`
      INSERT INTO daily_metrics (user_id, pain_level, swelling_status, rom_extension, rom_flexion, adherence, notes)
      VALUES (?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(user_id, date) 
      DO UPDATE SET 
        pain_level = excluded.pain_level,
        swelling_status = excluded.swelling_status,
        rom_extension = excluded.rom_extension,
        rom_flexion = excluded.rom_flexion,
        adherence = excluded.adherence,
        notes = excluded.notes,
        timestamp = DATETIME('now')
    `);

    try {
      const result = stmt.run(userId, painLevel, swellingStatus, romExtension, romFlexion, adherence ? 1 : 0, notes);
      
      console.log(`[DATABASE] Logged metrics for user ${userId}`);
      
      return {
        success: true,
        message: `✅ Metrics logged successfully!\n\n📊 Today's Check-in:\n• Pain: ${painLevel}/10\n• Swelling: ${swellingStatus}\n• ROM: ${romExtension}° extension, ${romFlexion}° flexion\n• Exercises: ${adherence ? 'Completed ✓' : 'Not done ✗'}`,
        data: {
          userId,
          date: new Date().toISOString().split('T')[0],
          painLevel,
          swellingStatus,
          romExtension,
          romFlexion,
          adherence
        }
      };
    } catch (error) {
      console.error('[DATABASE] Error logging metrics:', error);
      return {
        success: false,
        message: `❌ Error logging metrics: ${error.message}`
      };
    }
  }

  /**
   * Get latest metrics for a user
   */
  getLatestMetrics(userId) {
    const stmt = this.db.prepare(`
      SELECT * FROM daily_metrics
      WHERE user_id = ?
      ORDER BY date DESC
      LIMIT 1
    `);

    return stmt.get(userId);
  }

  /**
   * Get metrics history for a user (last N days)
   */
  getMetricsHistory(userId, days = 7) {
    const stmt = this.db.prepare(`
      SELECT * FROM daily_metrics
      WHERE user_id = ?
      ORDER BY date DESC
      LIMIT ?
    `);

    return stmt.all(userId, days);
  }

  /**
   * Get or create user configuration
   */
  getUserConfig(userId) {
    const stmt = this.db.prepare(`
      SELECT * FROM user_config WHERE user_id = ?
    `);

    return stmt.get(userId);
  }

  /**
   * Set user surgery date
   */
  setSurgeryDate(userId, surgeryDate, surgeonName = null, surgeryType = 'ACL Reconstruction') {
    const stmt = this.db.prepare(`
      INSERT INTO user_config (user_id, surgery_date, surgeon_name, surgery_type)
      VALUES (?, ?, ?, ?)
      ON CONFLICT(user_id)
      DO UPDATE SET
        surgery_date = excluded.surgery_date,
        surgeon_name = excluded.surgeon_name,
        surgery_type = excluded.surgery_type,
        updated_at = DATETIME('now')
    `);

    stmt.run(userId, surgeryDate, surgeonName, surgeryType);
    console.log(`[DATABASE] Set surgery date for ${userId}: ${surgeryDate}`);
  }

  /**
   * Calculate metrics trends
   */
  getMetricsTrends(userId, days = 7) {
    const history = this.getMetricsHistory(userId, days);
    
    if (history.length < 2) {
      return null;
    }

    const latest = history[0];
    const previous = history[1];

    return {
      painTrend: latest.pain_level - previous.pain_level,
      romExtensionTrend: latest.rom_extension - previous.rom_extension,
      romFlexionTrend: latest.rom_flexion - previous.rom_flexion,
      swellingTrend: latest.swelling_status === 'better' ? 1 : (latest.swelling_status === 'worse' ? -1 : 0),
      adherenceRate: history.filter(m => m.adherence).length / history.length
    };
  }

  /**
   * Close database connection
   */
  close() {
    if (this.db) {
      this.db.close();
      console.log('[DATABASE] Connection closed');
    }
  }
}

export default DatabaseManager;
