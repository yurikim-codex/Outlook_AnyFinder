"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[M10] SQLite DB 연결 & 스키마 관리 (v3 — 스레드 안전)
"""

import sqlite3
import os
from pathlib import Path

DATA_DIR = Path.home() / ".outlook_anyfinder"
DB_PATH = DATA_DIR / "anyfinder.db"


def get_db_path() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DB_PATH


def get_connection(db_path: Path = None) -> sqlite3.Connection:
    """SQLite 연결 생성 (스레드 안전: check_same_thread=False)"""
    if db_path is None:
        db_path = get_db_path()

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA cache_size=-64000")
    return conn


def init_schema(conn: sqlite3.Connection):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS emails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_id TEXT UNIQUE NOT NULL,
        subject TEXT DEFAULT '',
        sender_name TEXT DEFAULT '',
        sender_email TEXT DEFAULT '',
        recipients TEXT DEFAULT '',
        cc TEXT DEFAULT '',
        body_text TEXT DEFAULT '',
        folder_name TEXT DEFAULT '',
        received_at TEXT,
        sent_at TEXT,
        has_attachments INTEGER DEFAULT 0,
        attachment_count INTEGER DEFAULT 0,
        attachment_names TEXT DEFAULT '',
        attachment_types TEXT DEFAULT '',
        importance INTEGER DEFAULT 1,
        is_read INTEGER DEFAULT 1,
        categories TEXT DEFAULT '',
        conversation_id TEXT DEFAULT '',
        indexed_at TEXT DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_emails_received ON emails(received_at DESC);
    CREATE INDEX IF NOT EXISTS idx_emails_folder ON emails(folder_name);
    CREATE INDEX IF NOT EXISTS idx_emails_sender ON emails(sender_email);
    CREATE INDEX IF NOT EXISTS idx_emails_entry ON emails(entry_id);
    CREATE INDEX IF NOT EXISTS idx_emails_has_att ON emails(has_attachments);
    CREATE INDEX IF NOT EXISTS idx_emails_importance ON emails(importance);

    CREATE TABLE IF NOT EXISTS search_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword TEXT UNIQUE NOT NULL,
        search_count INTEGER DEFAULT 1,
        last_searched_at TEXT DEFAULT (datetime('now')),
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS bookmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        query TEXT NOT NULL,
        filters TEXT DEFAULT '{}',
        position INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS search_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        keyword TEXT NOT NULL,
        searched_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_sessions_keyword ON search_sessions(keyword);
    CREATE INDEX IF NOT EXISTS idx_sessions_sid ON search_sessions(session_id);

    CREATE TABLE IF NOT EXISTS related_keywords (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword TEXT NOT NULL,
        related TEXT NOT NULL,
        score REAL DEFAULT 1.0,
        source TEXT DEFAULT 'auto',
        UNIQUE(keyword, related)
    );
    CREATE INDEX IF NOT EXISTS idx_related_kw ON related_keywords(keyword);

    CREATE TABLE IF NOT EXISTS sync_meta (
        key TEXT PRIMARY KEY,
        value TEXT
    );

    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );

    CREATE TABLE IF NOT EXISTS email_hashes (
        entry_id TEXT PRIMARY KEY,
        content_hash TEXT NOT NULL
    );
    """)

    _create_fts5(conn)
    conn.commit()


def _create_fts5(conn):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='emails_fts'"
    ).fetchone()
    if row is not None:
        return

    conn.execute("""
        CREATE VIRTUAL TABLE emails_fts USING fts5(
            subject, sender_name, sender_email, recipients,
            body_text, attachment_names, categories,
            content=emails, content_rowid=id,
            tokenize='unicode61 remove_diacritics 2'
        )
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS emails_fts_ai AFTER INSERT ON emails BEGIN
            INSERT INTO emails_fts(rowid, subject, sender_name, sender_email,
                recipients, body_text, attachment_names, categories)
            VALUES (new.id, new.subject, new.sender_name, new.sender_email,
                new.recipients, new.body_text, new.attachment_names, new.categories);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS emails_fts_ad AFTER DELETE ON emails BEGIN
            INSERT INTO emails_fts(emails_fts, rowid, subject, sender_name,
                sender_email, recipients, body_text, attachment_names, categories)
            VALUES ('delete', old.id, old.subject, old.sender_name, old.sender_email,
                old.recipients, old.body_text, old.attachment_names, old.categories);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS emails_fts_au AFTER UPDATE ON emails BEGIN
            INSERT INTO emails_fts(emails_fts, rowid, subject, sender_name,
                sender_email, recipients, body_text, attachment_names, categories)
            VALUES ('delete', old.id, old.subject, old.sender_name, old.sender_email,
                old.recipients, old.body_text, old.attachment_names, old.categories);
            INSERT INTO emails_fts(rowid, subject, sender_name, sender_email,
                recipients, body_text, attachment_names, categories)
            VALUES (new.id, new.subject, new.sender_name, new.sender_email,
                new.recipients, new.body_text, new.attachment_names, new.categories);
        END
    """)


def init_db(db_path=None):
    conn = get_connection(db_path)
    init_schema(conn)
    return conn

# ─── 유틸리티 ───

def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM sync_meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default

def set_meta(conn, key, value):
    conn.execute("INSERT INTO sync_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=?", (key, value, value))
    conn.commit()

def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default

def set_setting(conn, key, value):
    conn.execute("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=?", (key, value, value))
    conn.commit()

def get_email_count(conn):
    return conn.execute("SELECT COUNT(*) as cnt FROM emails").fetchone()["cnt"]

def email_exists(conn, entry_id):
    return conn.execute("SELECT 1 FROM emails WHERE entry_id=?", (entry_id,)).fetchone() is not None

def get_hash(conn, entry_id):
    row = conn.execute("SELECT content_hash FROM email_hashes WHERE entry_id=?", (entry_id,)).fetchone()
    return row["content_hash"] if row else None

def set_hash(conn, entry_id, content_hash):
    conn.execute("INSERT OR REPLACE INTO email_hashes(entry_id, content_hash) VALUES(?,?)", (entry_id, content_hash))

def delete_hash(conn, entry_id):
    conn.execute("DELETE FROM email_hashes WHERE entry_id=?", (entry_id,))

def get_all_hashes(conn):
    rows = conn.execute("SELECT entry_id, content_hash FROM email_hashes").fetchall()
    return {r["entry_id"]: r["content_hash"] for r in rows}

def cleanup_session_logs(conn, max_rows=1000):
    conn.execute(f"""
        DELETE FROM search_sessions WHERE id NOT IN (
            SELECT id FROM search_sessions ORDER BY searched_at DESC LIMIT {max_rows}
        )
    """)
    conn.commit()
