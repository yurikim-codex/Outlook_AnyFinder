"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[C14] 성능 벤치마크 테스트

SLA 기준:
  - 검색 응답: < 100ms
  - 자동완성: < 50ms
  - 인덱싱 속도: ≥ 5건/초 (Mock 환경, COM 없이)
"""

import pytest
import time
import tempfile
from pathlib import Path

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.database import init_db
from core.outlook_connector import MockOutlookConnector, OlDefaultFolders
from core.index_builder import IndexBuilder
from core.search_engine import SearchEngine
from core.autocomplete import AutocompleteEngine
from core.sync_manager import MockSyncManager


@pytest.fixture(scope="module")
def perf_env():
    """성능 테스트용 환경 (모듈 스코프 — 한 번만 생성)"""
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

    yield {
        "conn": conn, "mock": mock,
        "engine": SearchEngine(conn),
        "ac": AutocompleteEngine(conn),
        "total": len(all_mails),
    }
    conn.close()
    db_path.unlink(missing_ok=True)


class TestSearchPerformance:

    @pytest.mark.parametrize("query", [
        "프로젝트", "견적서", "보고서", "회의", "예산",
        "from:김철수", "subject:견적서",
        "프로젝트 보고서", "from:김철수 견적서",
    ])
    def test_search_under_100ms(self, perf_env, query):
        """각 검색 쿼리가 100ms 이내"""
        eng = perf_env["engine"]
        start = time.perf_counter()
        resp = eng.search(query)
        ms = (time.perf_counter() - start) * 1000
        print(f"  검색 '{query}': {resp.total_count}건 / {ms:.1f}ms")
        assert ms < 100, f"검색 시간 초과: {ms:.1f}ms (쿼리: {query})"

    def test_empty_search_speed(self, perf_env):
        """빈 검색 (전체 조회) 100ms 이내"""
        start = time.perf_counter()
        resp = perf_env["engine"].search("")
        ms = (time.perf_counter() - start) * 1000
        print(f"  빈 검색: {resp.total_count}건 / {ms:.1f}ms")
        assert ms < 100

    def test_filtered_search_speed(self, perf_env):
        """필터 + 키워드 조합 100ms 이내"""
        start = time.perf_counter()
        resp = perf_env["engine"].search("견적서", extra_where=[
            ("folder_name = ?", ["받은편지함"]),
            ("has_attachments = ?", [1]),
        ])
        ms = (time.perf_counter() - start) * 1000
        print(f"  필터 검색: {resp.total_count}건 / {ms:.1f}ms")
        assert ms < 100


class TestAutocompletePerformance:

    def test_autocomplete_under_50ms(self, perf_env):
        """자동완성 응답 50ms 이내"""
        ac = perf_env["ac"]
        # 히스토리 채우기
        for kw in ["프로젝트 보고서", "프로젝트 견적서", "프로모션", "프로세스", "프로그램"]:
            ac.record_search(kw)

        start = time.perf_counter()
        result = ac.get_suggestions("프로")
        ms = (time.perf_counter() - start) * 1000
        print(f"  자동완성 '프로': {len(result)}건 / {ms:.1f}ms")
        assert ms < 50


class TestIndexingPerformance:

    def test_indexing_speed(self, perf_env):
        """인덱싱 속도 ≥ 5건/초 (Mock 환경)"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        conn = init_db(db_path)
        builder = IndexBuilder(conn)
        mock = perf_env["mock"]

        mails = list(mock.iter_mails(OlDefaultFolders.INBOX)) + list(mock.iter_mails(OlDefaultFolders.SENT))

        start = time.perf_counter()
        stats = builder.build_from_iterator(iter(mails), len(mails))
        elapsed = time.perf_counter() - start

        speed = stats["indexed"] / elapsed if elapsed > 0 else 0
        print(f"  인덱싱: {stats['indexed']}건 / {elapsed:.2f}초 = {speed:.1f}건/초")
        assert speed >= 5, f"인덱싱 속도 부족: {speed:.1f}건/초"

        conn.close()
        db_path.unlink(missing_ok=True)


class TestSyncPerformance:

    def test_no_changes_sync_fast(self, perf_env):
        """변경 없는 동기화는 빠르게 완료"""
        sm = MockSyncManager(perf_env["conn"], perf_env["mock"])

        start = time.perf_counter()
        plan = sm.create_plan(folder_ids=[6, 5])
        ms = (time.perf_counter() - start) * 1000

        print(f"  동기화 계획: {plan.total_outlook}건 스캔 / {ms:.1f}ms / 변경={plan.has_changes}")
        assert not plan.has_changes
        assert ms < 500  # 500ms 이내


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
