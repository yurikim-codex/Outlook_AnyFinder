"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[C07~C08] 메인 화면 통합 흐름 테스트

GUI 없이 검색→결과→미리보기 데이터 흐름을 검증합니다.
"""

import pytest
import tempfile
from pathlib import Path

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.database import init_db, get_email_count
from data.models import SearchResult
from core.outlook_connector import MockOutlookConnector, OlDefaultFolders
from core.index_builder import IndexBuilder
from core.search_engine import SearchEngine
from core.query_parser import parse_query
from utils.date_utils import format_display_date, get_date_filter_range


@pytest.fixture
def full_env():
    """Mock 데이터가 인덱싱된 전체 환경"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    conn = init_db(db_path)

    mock = MockOutlookConnector()
    mock.connect()
    builder = IndexBuilder(conn)

    inbox = list(mock.iter_mails(OlDefaultFolders.INBOX))
    sent = list(mock.iter_mails(OlDefaultFolders.SENT))
    all_mails = inbox + sent
    builder.build_from_iterator(iter(all_mails), len(all_mails))

    engine = SearchEngine(conn)

    yield {
        "conn": conn,
        "engine": engine,
        "connector": mock,
        "total": len(all_mails),
        "inbox_count": len(inbox),
        "sent_count": len(sent),
    }

    conn.close()
    db_path.unlink(missing_ok=True)


class TestSearchResultFlow:
    """검색 결과 데이터 흐름 테스트"""

    def test_01_search_returns_searchresult(self, full_env):
        """검색 결과가 SearchResult 객체 리스트여야 한다"""
        resp = full_env["engine"].search("프로젝트")
        assert len(resp.results) > 0
        for r in resp.results:
            assert isinstance(r, SearchResult)
            assert r.email.entry_id != ""

    def test_02_result_has_all_display_fields(self, full_env):
        """결과 카드에 표시할 모든 필드가 있어야 한다"""
        resp = full_env["engine"].search("프로젝트")
        r = resp.results[0]

        # 필수 표시 필드
        assert r.email.subject != ""
        assert r.email.sender_name != ""
        assert r.email.received_at != ""
        assert r.email.folder_name != ""
        assert r.email.entry_id != ""

    def test_03_result_with_attachment_info(self, full_env):
        """첨부파일 있는 메일의 첨부 정보"""
        resp = full_env["engine"].search("견적서")
        att_results = [r for r in resp.results if r.email.has_attachments]
        assert len(att_results) > 0
        for r in att_results:
            assert r.email.attachment_names != ""
            assert r.email.attachment_count > 0

    def test_04_preview_data(self, full_env):
        """미리보기에 필요한 데이터가 모두 있어야 한다"""
        resp = full_env["engine"].search("보고서")
        r = resp.results[0]

        # 미리보기에 표시되는 항목
        assert r.email.subject != ""
        assert r.email.sender_name != ""
        assert r.email.sender_email != ""
        assert r.email.received_at != ""
        assert r.email.body_text != ""

    def test_05_folder_filter_via_where(self, full_env):
        """폴더 필터가 WHERE 절로 정상 동작"""
        resp = full_env["engine"].search(
            "", extra_where=[("folder_name = ?", ["받은편지함"])]
        )
        assert resp.total_count == full_env["inbox_count"]
        for r in resp.results:
            assert r.email.folder_name == "받은편지함"

    def test_06_sent_folder_filter(self, full_env):
        """보낸편지함 필터"""
        resp = full_env["engine"].search(
            "", extra_where=[("folder_name = ?", ["보낸편지함"])]
        )
        assert resp.total_count == full_env["sent_count"]

    def test_07_attachment_filter(self, full_env):
        """첨부파일 필터"""
        resp = full_env["engine"].search(
            "", extra_where=[("has_attachments = ?", [1])]
        )
        for r in resp.results:
            assert r.email.has_attachments == 1

    def test_08_combined_search_and_filter(self, full_env):
        """검색어 + 폴더 + 첨부 결합"""
        resp = full_env["engine"].search(
            "견적서",
            extra_where=[
                ("folder_name = ?", ["받은편지함"]),
                ("has_attachments = ?", [1])
            ]
        )
        for r in resp.results:
            assert r.email.folder_name == "받은편지함"
            assert r.email.has_attachments == 1

    def test_09_sort_newest_first(self, full_env):
        """최신순 정렬"""
        resp = full_env["engine"].search("", sort_by="received_at_desc")
        if len(resp.results) >= 2:
            dates = [r.email.received_at for r in resp.results]
            assert dates == sorted(dates, reverse=True)

    def test_10_search_response_metadata(self, full_env):
        """SearchResponse 메타데이터 정확성"""
        resp = full_env["engine"].search("프로젝트", page=1, per_page=5)
        assert resp.page == 1
        assert resp.per_page == 5
        assert resp.total_count >= 1
        assert resp.elapsed_ms >= 0
        assert resp.query == "프로젝트"


class TestFolderCounts:
    """폴더 카운트 테스트"""

    def test_11_folder_counts(self, full_env):
        counts = full_env["engine"].get_folder_counts()
        assert counts["받은편지함"] == full_env["inbox_count"]
        assert counts["보낸편지함"] == full_env["sent_count"]

    def test_12_total_count(self, full_env):
        assert full_env["engine"].get_total_count() == full_env["total"]


class TestDateUtils:
    """날짜 유틸리티 테스트"""

    def test_13_format_display_date(self):
        result = format_display_date("2026-05-27 14:30:00")
        assert result != ""
        assert len(result) > 0

    def test_14_date_filter_range(self):
        start, end = get_date_filter_range("최근 7일")
        assert start is not None
        assert end is not None

    def test_15_date_filter_all(self):
        start, end = get_date_filter_range("전체 기간")
        assert start is None
        assert end is None


class TestOpenInOutlook:
    """Outlook 열기 테스트"""

    def test_16_mock_open(self, full_env):
        """Mock 커넥터에서 열기 (에러 없이)"""
        resp = full_env["engine"].search("프로젝트")
        entry_id = resp.results[0].email.entry_id
        full_env["connector"].open_mail_in_outlook(entry_id)  # 에러 없으면 성공


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
