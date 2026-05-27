"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[C01] DB 스키마 생성 & CRUD 테스트
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.database import get_connection, init_schema, init_db, get_meta, set_meta, get_email_count, email_exists
from data.models import EmailRecord, Bookmark, SearchHistoryItem


@pytest.fixture
def db():
    """테스트용 임시 DB"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    conn = init_db(db_path)
    yield conn
    conn.close()
    db_path.unlink(missing_ok=True)


class TestSchemaCreation:
    """스키마 생성 테스트"""

    def test_01_db_file_created(self, db):
        """DB 파일이 생성되어야 한다"""
        assert db is not None

    def test_02_emails_table_exists(self, db):
        """emails 테이블이 존재해야 한다"""
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='emails'"
        ).fetchone()
        assert row is not None

    def test_03_emails_fts_table_exists(self, db):
        """emails_fts FTS5 가상 테이블이 존재해야 한다"""
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='emails_fts'"
        ).fetchone()
        assert row is not None

    def test_04_search_history_table_exists(self, db):
        """search_history 테이블이 존재해야 한다"""
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='search_history'"
        ).fetchone()
        assert row is not None

    def test_05_bookmarks_table_exists(self, db):
        """bookmarks 테이블이 존재해야 한다"""
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bookmarks'"
        ).fetchone()
        assert row is not None

    def test_06_related_keywords_table_exists(self, db):
        """related_keywords 테이블이 존재해야 한다"""
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='related_keywords'"
        ).fetchone()
        assert row is not None

    def test_07_sync_meta_table_exists(self, db):
        """sync_meta 테이블이 존재해야 한다"""
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sync_meta'"
        ).fetchone()
        assert row is not None

    def test_08_search_sessions_table_exists(self, db):
        """search_sessions 테이블이 존재해야 한다"""
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='search_sessions'"
        ).fetchone()
        assert row is not None

    def test_09_app_settings_table_exists(self, db):
        """app_settings 테이블이 존재해야 한다"""
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='app_settings'"
        ).fetchone()
        assert row is not None


class TestEmailsCRUD:
    """emails 테이블 CRUD 테스트"""

    def _make_email(self, entry_id="test_001", subject="테스트 메일"):
        return EmailRecord(
            entry_id=entry_id,
            subject=subject,
            sender_name="김철수",
            sender_email="kim@company.com",
            recipients="나",
            cc="",
            body_text="이것은 테스트 메일 본문입니다.",
            folder_name="받은편지함",
            received_at="2026-05-27T14:30:00",
            sent_at="2026-05-27T14:29:00",
            has_attachments=1,
            attachment_count=1,
            attachment_names="견적서.xlsx",
            attachment_types=".xlsx",
            importance=2,
            is_read=1,
            categories="업무",
            conversation_id="conv_001",
        )

    def test_10_insert_email(self, db):
        """메일 INSERT 후 SELECT 결과가 일치해야 한다"""
        email = self._make_email()
        db.execute(EmailRecord.insert_sql(), email.to_insert_tuple())
        db.commit()

        row = db.execute("SELECT * FROM emails WHERE entry_id=?", ("test_001",)).fetchone()
        assert row is not None
        assert row["subject"] == "테스트 메일"
        assert row["sender_name"] == "김철수"
        assert row["has_attachments"] == 1
        assert row["attachment_names"] == "견적서.xlsx"

    def test_11_entry_id_unique(self, db):
        """동일 entry_id로 중복 INSERT 시 무시되어야 한다 (INSERT OR IGNORE)"""
        email = self._make_email("dup_001", "원본 메일")
        db.execute(EmailRecord.insert_sql(), email.to_insert_tuple())
        db.commit()

        email2 = self._make_email("dup_001", "중복 메일")
        db.execute(EmailRecord.insert_sql(), email2.to_insert_tuple())
        db.commit()

        rows = db.execute("SELECT * FROM emails WHERE entry_id=?", ("dup_001",)).fetchall()
        assert len(rows) == 1
        assert rows[0]["subject"] == "원본 메일"  # 첫 번째 것 유지

    def test_12_fts5_trigger_works(self, db):
        """emails INSERT 시 FTS5 인덱스에 자동 추가되어야 한다"""
        email = self._make_email("fts_001", "프로젝트 진행 보고서")
        db.execute(EmailRecord.insert_sql(), email.to_insert_tuple())
        db.commit()

        # FTS5 검색
        rows = db.execute(
            "SELECT rowid FROM emails_fts WHERE emails_fts MATCH '프로젝트'"
        ).fetchall()
        assert len(rows) >= 1

    def test_13_fts5_search_body(self, db):
        """본문 내용으로 FTS5 검색이 되어야 한다"""
        email = self._make_email("fts_002", "일반 제목")
        email.body_text = "2분기 예산 집행 현황을 보고드립니다"
        db.execute(EmailRecord.insert_sql(), email.to_insert_tuple())
        db.commit()

        rows = db.execute(
            "SELECT rowid FROM emails_fts WHERE emails_fts MATCH '예산'"
        ).fetchall()
        assert len(rows) >= 1

    def test_14_email_count(self, db):
        """get_email_count가 정확한 수를 반환해야 한다"""
        for i in range(5):
            email = self._make_email(f"cnt_{i}", f"메일 {i}")
            db.execute(EmailRecord.insert_sql(), email.to_insert_tuple())
        db.commit()
        assert get_email_count(db) == 5

    def test_15_email_exists(self, db):
        """email_exists가 올바르게 동작해야 한다"""
        email = self._make_email("exist_001")
        db.execute(EmailRecord.insert_sql(), email.to_insert_tuple())
        db.commit()
        assert email_exists(db, "exist_001") is True
        assert email_exists(db, "not_exist") is False

    def test_16_from_row(self, db):
        """EmailRecord.from_row가 올바르게 변환해야 한다"""
        email = self._make_email("row_001", "변환 테스트")
        db.execute(EmailRecord.insert_sql(), email.to_insert_tuple())
        db.commit()

        row = db.execute("SELECT * FROM emails WHERE entry_id=?", ("row_001",)).fetchone()
        record = EmailRecord.from_row(row)
        assert record.entry_id == "row_001"
        assert record.subject == "변환 테스트"
        assert record.sender_name == "김철수"
        assert record.id is not None


class TestMetaAndSettings:
    """sync_meta & app_settings 테스트"""

    def test_17_set_and_get_meta(self, db):
        """sync_meta 저장/조회"""
        set_meta(db, "last_sync_time", "2026-05-27T14:30:00")
        assert get_meta(db, "last_sync_time") == "2026-05-27T14:30:00"

    def test_18_meta_upsert(self, db):
        """sync_meta 업데이트 (upsert)"""
        set_meta(db, "test_key", "value_1")
        set_meta(db, "test_key", "value_2")
        assert get_meta(db, "test_key") == "value_2"

    def test_19_meta_default(self, db):
        """존재하지 않는 키 조회 시 기본값"""
        assert get_meta(db, "nonexistent") is None
        assert get_meta(db, "nonexistent", "default") == "default"

    def test_20_schema_idempotent(self, db):
        """init_schema를 여러 번 호출해도 에러 없어야 한다"""
        init_schema(db)  # 두 번째 호출
        init_schema(db)  # 세 번째 호출
        assert get_email_count(db) >= 0  # 에러 없으면 성공


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
