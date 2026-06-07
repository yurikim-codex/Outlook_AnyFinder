"""
OutLook AnyFinder Ver0.9.1.1 for SESUNG Team
[M10] SQLite DB 연결 & 스키마 관리 (v3 — 스레드 안전)

v3.1: 폴더명 별칭 유틸리티 추가 — Outlook 환경별 폴더명 변형을 단일 인터페이스로 통합
"""

import sqlite3
import os
import time
from pathlib import Path
from typing import List, Dict

DATA_DIR = Path.home() / ".outlook_anyfinder"
DB_PATH = DATA_DIR / "anyfinder.db"

# ─── 폴더명 별칭 (Outlook 환경별 변형 통합) ───

# 폴더 ID → 퀴리용 별칭 리스트 (DB 쿼리에서 folder_name IN (...) 으로 사용)
FOLDER_ALIASES: Dict[int, List[str]] = {
    6:  ["받은편지함", "받은 편지함", "Inbox"],
    5:  ["보낸편지함", "보낸 편지함", "Sent Items", "Sent"],
    16: ["임시보관함", "임시 보관함", "Drafts"],
    3:  ["지운편지함", "지운 편지함", "Deleted Items", "Trash"],
}

# 사이드바 키 → 별칭 리스트 (UI 표시용)
SIDEBAR_FOLDER_ALIASES: Dict[str, List[str]] = {
    "inbox":  ["받은편지함", "받은 편지함", "Inbox"],
    "sent":   ["보낸편지함", "보낸 편지함", "Sent Items", "Sent"],
    "drafts": ["임시보관함", "임시 보관함", "Drafts"],
    "trash":  ["지운편지함", "지운 편지함", "Deleted Items", "Trash"],
}

# UI 표시용 폴더명 → 별칭 리스트
UI_FOLDER_ALIASES: Dict[str, List[str]] = {
    "받은편지함": ["받은편지함", "받은 편지함", "Inbox"],
    "보낸편지함": ["보낸편지함", "보낸 편지함", "Sent Items", "Sent"],
    "임시보관함": ["임시보관함", "임시 보관함", "Drafts"],
    "지운편지함": ["지운편지함", "지운 편지함", "Deleted Items", "Trash"],
}


def get_folder_aliases(folder_id: int) -> List[str]:
    """폴더 ID에 해당하는 모든 별칭 반환. 없으면 빈 리스트."""
    return FOLDER_ALIASES.get(folder_id, [])


def get_sidebar_aliases(key: str) -> List[str]:
    """사이드바 키에 해당하는 모든 별칭 반환."""
    return SIDEBAR_FOLDER_ALIASES.get(key, [key])


def get_ui_folder_aliases(folder_name: str) -> List[str]:
    """UI 표시 폴더명에 해당하는 모든 별칭 반환."""
    return UI_FOLDER_ALIASES.get(folder_name, [folder_name])


def get_all_known_folder_names() -> set:
    """알려진 모든 폴더명(별칭 포함) 집합 반환."""
    names = set()
    for aliases in FOLDER_ALIASES.values():
        names.update(aliases)
    return names


def build_folder_where_clause(folder_ids: List[int]) -> tuple:
    """폴더 ID 목록으로 (clause, params) 생성. 모든 별칭 포함.
    folder_ids가 None이거나 비어있으면 필터 없음 (전체)."""
    if not folder_ids:
        return ("1=1", [])
    all_names = []
    for fid in folder_ids:
        all_names.extend(get_folder_aliases(fid))
    if not all_names:
        return ("1=0", [])
    placeholders = ",".join("?" for _ in all_names)
    return (f"folder_name IN ({placeholders})", all_names)


def get_db_path() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DB_PATH


def get_connection(db_path: Path = None) -> sqlite3.Connection:
    """SQLite 연결 생성 (스레드 안전: check_same_thread=False)"""
    if db_path is None:
        db_path = get_db_path()

    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
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
    for attempt in range(5):
        try:
            conn.execute("INSERT INTO sync_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=?", (key, value, value))
            conn.commit()
            return
        except sqlite3.OperationalError as e:
            if "locked" not in str(e).lower() or attempt == 4:
                raise
            time.sleep(0.3 * (attempt + 1))

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


def clear_search_records(conn):
    """검색 기록을 초기화한다. 북마크는 유지한다."""
    conn.execute("DELETE FROM search_history")
    conn.execute("DELETE FROM search_sessions")
    conn.execute("DELETE FROM related_keywords")
    conn.commit()


def get_mock_email_count(conn) -> int:
    """Mock/Demo 메일 개수 반환."""
    try:
        row = conn.execute("SELECT COUNT(*) as cnt FROM emails WHERE entry_id LIKE 'MOCK_%'").fetchone()
        return row["cnt"] if row else 0
    except Exception:
        return 0


def purge_mock_data(conn) -> int:
    """실제 Outlook 동기화를 방해할 수 있는 Mock/Demo 메일과 해시를 삭제한다."""
    mock_count = get_mock_email_count(conn)
    if mock_count <= 0:
        return 0
    conn.execute("DELETE FROM emails WHERE entry_id LIKE 'MOCK_%'")
    conn.execute("DELETE FROM email_hashes WHERE entry_id LIKE 'MOCK_%'")
    # Mock 인덱싱 때 저장된 동기화 메타가 있으면 실제 Outlook 증분 동기화를 방해할 수 있다.
    conn.execute("DELETE FROM sync_meta WHERE key IN ('last_sync_time', 'total_indexed', 'indexing_state')")
    try:
        conn.execute("INSERT INTO emails_fts(emails_fts) VALUES('rebuild')")
    except Exception:
        pass
    conn.commit()
    return mock_count
