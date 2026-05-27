"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[C02] Outlook → DB 파이프라인 테스트

MockOutlookConnector → mail_extractor → index_builder → DB 검증
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.database import init_db, get_email_count, email_exists, get_meta
from data.models import EmailRecord
from core.outlook_connector import MockOutlookConnector, OlDefaultFolders, create_connector
from core.mail_extractor import extract_to_record, _clean_text, _clean_plain_text
from core.index_builder import IndexBuilder


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    conn = init_db(db_path)
    yield conn
    conn.close()
    db_path.unlink(missing_ok=True)


@pytest.fixture
def mock_connector():
    conn = MockOutlookConnector()
    conn.connect()
    return conn


# ═══════════════════════════════════════════
#  MockOutlookConnector 테스트
# ═══════════════════════════════════════════

class TestMockConnector:

    def test_01_connect(self, mock_connector):
        """Mock 연결 성공"""
        assert mock_connector.is_connected is True

    def test_02_folder_list(self, mock_connector):
        """폴더 목록 반환"""
        folders = mock_connector.get_folder_list()
        assert len(folders) >= 2
        names = [f["name"] for f in folders]
        assert "받은편지함" in names
        assert "보낸편지함" in names

    def test_03_total_count(self, mock_connector):
        """전체 메일 수 > 0"""
        count = mock_connector.get_total_mail_count()
        assert count > 0

    def test_04_iter_inbox(self, mock_connector):
        """받은편지함 메일 순회"""
        mails = list(mock_connector.iter_mails(OlDefaultFolders.INBOX))
        assert len(mails) > 0
        for mail in mails:
            assert mail["folder_name"] == "받은편지함"
            assert mail["entry_id"] != ""
            assert mail["subject"] != ""

    def test_05_iter_sent(self, mock_connector):
        """보낸편지함 메일 순회"""
        mails = list(mock_connector.iter_mails(OlDefaultFolders.SENT))
        assert len(mails) > 0
        for mail in mails:
            assert mail["folder_name"] == "보낸편지함"

    def test_06_mail_has_required_fields(self, mock_connector):
        """메일 데이터에 필수 필드 존재"""
        mails = list(mock_connector.iter_mails(OlDefaultFolders.INBOX))
        required = [
            "entry_id", "subject", "sender_name", "sender_email",
            "recipients", "body_text", "folder_name", "received_at",
            "has_attachments", "attachment_names", "attachment_types",
        ]
        for mail in mails[:3]:
            for field in required:
                assert field in mail, f"필수 필드 '{field}' 없음"


# ═══════════════════════════════════════════
#  mail_extractor 테스트
# ═══════════════════════════════════════════

class TestMailExtractor:

    def test_07_extract_to_record(self, mock_connector):
        """raw dict → EmailRecord 변환"""
        mails = list(mock_connector.iter_mails(OlDefaultFolders.INBOX))
        record = extract_to_record(mails[0])
        assert record is not None
        assert isinstance(record, EmailRecord)
        assert record.entry_id != ""
        assert record.subject != ""
        assert record.sender_name != ""

    def test_08_extract_no_entry_id(self):
        """entry_id 없는 메일 → None"""
        raw = {"subject": "테스트"}
        record = extract_to_record(raw)
        assert record is None

    def test_09_extract_html_body(self):
        """HTML 본문이 있으면 평문으로 변환"""
        raw = {
            "entry_id": "html_test_001",
            "subject": "HTML 테스트",
            "body_text": "",
            "html_body": "<p>안녕하세요</p><br><b>굵은 글씨</b>",
            "sender_name": "테스터",
            "sender_email": "test@test.com",
            "recipients": "나",
            "folder_name": "받은편지함",
            "received_at": "2026-05-27 10:00:00",
        }
        record = extract_to_record(raw)
        assert record is not None
        assert "안녕하세요" in record.body_text
        assert "<p>" not in record.body_text  # HTML 태그 제거

    def test_10_clean_text(self):
        """텍스트 정제"""
        assert _clean_text("  공백  ") == "공백"
        assert _clean_text(None) == ""
        assert _clean_text("") == ""
        assert _clean_text("NULL\x00문자") == "NULL문자"

    def test_11_to_insert_tuple(self, mock_connector):
        """EmailRecord → INSERT 튜플 변환"""
        mails = list(mock_connector.iter_mails(OlDefaultFolders.INBOX))
        record = extract_to_record(mails[0])
        tup = record.to_insert_tuple()
        assert isinstance(tup, tuple)
        assert len(tup) == 18  # INSERT SQL의 ? 개수


# ═══════════════════════════════════════════
#  IndexBuilder 테스트
# ═══════════════════════════════════════════

class TestIndexBuilder:

    def test_12_build_from_mock(self, db, mock_connector):
        """Mock 메일을 인덱싱하고 DB에 저장"""
        builder = IndexBuilder(db)
        iterator = mock_connector.iter_mails(OlDefaultFolders.INBOX)
        total = mock_connector.get_total_mail_count()

        progress_log = []

        def on_progress(done, total, subject):
            progress_log.append((done, total, subject))

        stats = builder.build_from_iterator(
            mail_iterator=iterator,
            total_count=total,
            on_progress=on_progress,
        )

        assert stats["indexed"] > 0
        assert stats["errors"] == 0
        assert get_email_count(db) == stats["indexed"]

    def test_13_duplicate_prevention(self, db, mock_connector):
        """동일 메일 재인덱싱 시 중복 방지"""
        builder = IndexBuilder(db)

        # 1차 인덱싱
        mails = list(mock_connector.iter_mails(OlDefaultFolders.INBOX))
        stats1 = builder.build_from_iterator(iter(mails), len(mails))
        count_after_first = get_email_count(db)

        # 2차 인덱싱 (동일 메일)
        stats2 = builder.build_from_iterator(iter(mails), len(mails))
        count_after_second = get_email_count(db)

        assert count_after_second == count_after_first  # 증가 없음
        assert stats2["skipped"] == len(mails)  # 전부 건너뜀

    def test_14_fts5_search_after_index(self, db, mock_connector):
        """인덱싱 후 FTS5 검색 동작 확인"""
        builder = IndexBuilder(db)
        mails = list(mock_connector.iter_mails(OlDefaultFolders.INBOX))
        builder.build_from_iterator(iter(mails), len(mails))

        # "프로젝트" 검색
        rows = db.execute(
            "SELECT rowid FROM emails_fts WHERE emails_fts MATCH '프로젝트'"
        ).fetchall()
        assert len(rows) >= 1

        # "견적서" 검색
        rows = db.execute(
            "SELECT rowid FROM emails_fts WHERE emails_fts MATCH '견적서'"
        ).fetchall()
        assert len(rows) >= 1

    def test_15_stop_and_resume(self, db, mock_connector):
        """인덱싱 중단 후 재개 시 이어서 처리"""
        builder = IndexBuilder(db)
        mails = list(mock_connector.iter_mails(OlDefaultFolders.INBOX))

        # 5건만 인덱싱 후 중단
        stop_after = 5
        call_count = [0]

        def should_stop():
            call_count[0] += 1
            return call_count[0] > stop_after

        stats1 = builder.build_from_iterator(iter(mails), len(mails), should_stop=should_stop)
        first_count = get_email_count(db)
        assert first_count > 0
        assert first_count < len(mails)  # 전체보다 적어야 함

        # 나머지 인덱싱 (재개)
        stats2 = builder.build_from_iterator(iter(mails), len(mails))
        final_count = get_email_count(db)
        assert final_count == len(mails)  # 이제 전체 완료

    def test_16_sync_meta_updated(self, db, mock_connector):
        """인덱싱 완료 후 sync_meta 업데이트 확인"""
        builder = IndexBuilder(db)
        mails = list(mock_connector.iter_mails(OlDefaultFolders.INBOX))
        builder.build_from_iterator(iter(mails), len(mails))

        assert get_meta(db, "last_sync_time") is not None
        assert get_meta(db, "indexing_state") == "completed"

    def test_17_inbox_and_sent(self, db, mock_connector):
        """받은편지함 + 보낸편지함 동시 인덱싱"""
        builder = IndexBuilder(db)

        inbox = list(mock_connector.iter_mails(OlDefaultFolders.INBOX))
        sent = list(mock_connector.iter_mails(OlDefaultFolders.SENT))
        all_mails = inbox + sent

        stats = builder.build_from_iterator(iter(all_mails), len(all_mails))
        assert stats["indexed"] == len(all_mails)
        assert get_email_count(db) == len(all_mails)

        # 폴더별 카운트 확인
        inbox_count = db.execute(
            "SELECT COUNT(*) as cnt FROM emails WHERE folder_name='받은편지함'"
        ).fetchone()["cnt"]
        sent_count = db.execute(
            "SELECT COUNT(*) as cnt FROM emails WHERE folder_name='보낸편지함'"
        ).fetchone()["cnt"]

        assert inbox_count == len(inbox)
        assert sent_count == len(sent)


# ═══════════════════════════════════════════
#  create_connector 팩토리 테스트
# ═══════════════════════════════════════════

class TestConnectorFactory:

    def test_18_create_mock(self):
        """use_mock=True → MockOutlookConnector"""
        conn = create_connector(use_mock=True)
        assert isinstance(conn, MockOutlookConnector)

    def test_19_mock_connect_and_list(self):
        """Mock 커넥터 연결+폴더 목록 통합"""
        conn = create_connector(use_mock=True)
        conn.connect()
        folders = conn.get_folder_list()
        assert len(folders) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
