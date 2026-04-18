/**
 * Database Manager - SQLite Storage for Developer WhatsApp Assistant
 * 
 * Handles stateful memory and intent logging in Node.js.
 */

import Database from 'better-sqlite3';
import path from 'path';
import fs from 'fs';

export class DatabaseManager {
  constructor(dbPath = './data/dev_assistant.db') {
    this.dbPath = dbPath;
    this.db = null;
    
    this.init();
  }

  init() {
    // Ensure data directory exists
    const dataDir = path.dirname(this.dbPath);
    if (!fs.existsSync(dataDir)) {
      fs.mkdirSync(dataDir, { recursive: true });
    }

    // Connect to database
    this.db = new Database(this.dbPath);
    this.db.pragma('journal_mode = WAL');

    // Create tables
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        preferences TEXT DEFAULT '{}'
      );

      CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
      );

      CREATE TABLE IF NOT EXISTS intent_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        original_message TEXT NOT NULL,
        intent TEXT NOT NULL,
        topic TEXT NOT NULL,
        metadata_json TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
      );

      CREATE INDEX IF NOT EXISTS idx_messages_user_time ON messages(user_id, timestamp DESC);
      CREATE INDEX IF NOT EXISTS idx_intent_user_time ON intent_logs(user_id, timestamp DESC);
    `);

    console.log(`[DATABASE] Connected to ${this.dbPath}`);
  }

  getOrCreateUser(userId) {
    const stmt = this.db.prepare('SELECT * FROM users WHERE user_id = ?');
    const user = stmt.get(userId);

    if (user) {
      return {
        ...user,
        preferences: JSON.parse(user.preferences || '{}')
      };
    }

    const insertStmt = this.db.prepare('INSERT INTO users (user_id) VALUES (?)');
    insertStmt.run(userId);

    const newStmt = this.db.prepare('SELECT * FROM users WHERE user_id = ?');
    const newUser = newStmt.get(userId);

    return {
      ...newUser,
      preferences: JSON.parse(newUser.preferences || '{}')
    };
  }

  saveMessage(userId, role, content) {
    const stmt = this.db.prepare(
      'INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)'
    );
    stmt.run(userId, role, content);
  }

  getRecentMessages(userId, limit = 10) {
    const stmt = this.db.prepare(
      'SELECT role, content FROM messages WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?'
    );
    
    const rows = stmt.all(userId, limit);
    return rows.reverse().map(row => ({
      role: row.role,
      content: row.content
    }));
  }

  logIntent(userId, originalMessage, intent, topic, metadata) {
    const stmt = this.db.prepare(`
      INSERT INTO intent_logs 
      (user_id, original_message, intent, topic, metadata_json)
      VALUES (?, ?, ?, ?, ?)
    `);
    
    stmt.run(
      userId, 
      originalMessage, 
      intent, 
      topic, 
      JSON.stringify(metadata || {})
    );
  }

  close() {
    if (this.db) {
      this.db.close();
      console.log('[DATABASE] Connection closed');
    }
  }
}

export default DatabaseManager;
