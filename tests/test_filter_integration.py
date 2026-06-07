"""
OutLook AnyFinder Ver0.9.1.1 for SESUNG Team
[C11] 필터 고도화 통합 테스트
"""

import pytest
import tempfile
from pathlib import Path

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.database import init_db
from core.outlook_connector import MockOutlookConnector, OlDefaultFolders
from core.index_builder import IndexBuilder
from core.search_engine import SearchEngine


@pytest.fixture
def env():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    conn = init_db(db_path)
    mock = MockOutlookConnector()
    mock.connect()
    builder = IndexBuilder(conn)
    inbox = list(mock.iter_mails(OlDefaultFolders.INBOX))
    sent = list(mock.iter_mails(OlDefaultFolders.SENT))
    builder.build_from_iterator(iter(inbox + sent), len(inbox + sent))
    engine = SearchEngine(conn)
    yield engine, len(inbox), len(sent)
    conn.close()
    db_path.unlink(missing_ok=True)


class TestMultiFilter:

    def test_01_folder_inbox_only(self, env):
        eng, inbox_cnt, _ = env
        r = eng.search("", extra_where=[("folder_name = ?", ["받은편지함"])])
        assert r.total_count == inbox_cnt
        for res in r.results:
            assert res.email.folder_name == "받은편지함"

    def test_02_folder_sent_only(self, env):
        eng, _, sent_cnt = env
        r = eng.search("", extra_where=[("folder_name = ?", ["보낸편지함"])])
        assert r.total_count == sent_cnt

    def test_03_attachment_filter(self, env):
        eng, _, _ = env
        r = eng.search("", extra_where=[("has_attachments = ?", [1])])
        for res in r.results:
            assert res.email.has_attachments == 1

    def test_04_attachment_type_xlsx(self, env):
        eng, _, _ = env
        r = eng.search("", extra_where=[("attachment_types LIKE ?", ["%.xlsx%"])])
        for res in r.results:
            assert ".xlsx" in res.email.attachment_types

    def test_05_attachment_type_pdf(self, env):
        eng, _, _ = env
        r = eng.search("", extra_where=[("attachment_types LIKE ?", ["%.pdf%"])])
        for res in r.results:
            assert ".pdf" in res.email.attachment_types

    def test_06_unread_filter(self, env):
        eng, _, _ = env
        r = eng.search("", extra_where=[("is_read = ?", [0])])
        for res in r.results:
            assert res.email.is_read == 0

    def test_07_importance_high(self, env):
        eng, _, _ = env
        r = eng.search("", extra_where=[("importance = ?", [2])])
        for res in r.results:
            assert res.email.importance == 2

    def test_08_combined_folder_attachment(self, env):
        """받은편지함 + 첨부파일 있음"""
        eng, _, _ = env
        r = eng.search("", extra_where=[
            ("folder_name = ?", ["받은편지함"]),
            ("has_attachments = ?", [1])
        ])
        for res in r.results:
            assert res.email.folder_name == "받은편지함"
            assert res.email.has_attachments == 1

    def test_09_combined_keyword_folder_att_type(self, env):
        """키워드 + 받은편지함 + .xlsx"""
        eng, _, _ = env
        r = eng.search("견적서", extra_where=[
            ("folder_name = ?", ["받은편지함"]),
            ("attachment_types LIKE ?", ["%.xlsx%"]),
        ])
        for res in r.results:
            assert res.email.folder_name == "받은편지함"
            assert ".xlsx" in res.email.attachment_types

    def test_10_triple_filter(self, env):
        """받은편지함 + 첨부있음 + 중요:높음"""
        eng, _, _ = env
        r = eng.search("", extra_where=[
            ("folder_name = ?", ["받은편지함"]),
            ("has_attachments = ?", [1]),
            ("importance = ?", [2]),
        ])
        for res in r.results:
            assert res.email.folder_name == "받은편지함"
            assert res.email.has_attachments == 1
            assert res.email.importance == 2

    def test_11_no_match_returns_empty(self, env):
        """매칭 없는 필터 조합 → 빈 결과"""
        eng, _, _ = env
        r = eng.search("존재하지않는검색어xyz", extra_where=[
            ("folder_name = ?", ["보낸편지함"]),
            ("has_attachments = ?", [1]),
        ])
        assert r.total_count == 0

    def test_12_sort_newest_with_filter(self, env):
        """폴더 필터 + 최신순 정렬"""
        eng, _, _ = env
        r = eng.search("", sort_by="received_at_desc",
                        extra_where=[("folder_name = ?", ["받은편지함"])])
        if len(r.results) >= 2:
            dates = [res.email.received_at for res in r.results]
            assert dates == sorted(dates, reverse=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
