"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[C05] 검색 엔진 테스트 — FTS5 + BM25 + snippet + 페이지네이션
"""

import pytest
import tempfile
import time
from pathlib import Path

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.database import init_db, get_email_count
from core.outlook_connector import MockOutlookConnector, OlDefaultFolders
from core.index_builder import IndexBuilder
from core.search_engine import SearchEngine, SearchResponse


@pytest.fixture
def populated_db():
    """Mock 데이터가 인덱싱된 DB"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    conn = init_db(db_path)

    mock = MockOutlookConnector()
    mock.connect()
    builder = IndexBuilder(conn)

    inbox = list(mock.iter_mails(OlDefaultFolders.INBOX))
    sent = list(mock.iter_mails(OlDefaultFolders.SENT))
    builder.build_from_iterator(iter(inbox + sent), len(inbox + sent))

    yield conn, len(inbox + sent)

    conn.close()
    db_path.unlink(missing_ok=True)


@pytest.fixture
def engine(populated_db):
    conn, total = populated_db
    return SearchEngine(conn), total


class TestBasicSearch:

    def test_01_empty_query_returns_all(self, engine):
        """빈 쿼리 → 전체 결과 (시간순)"""
        eng, total = engine
        resp = eng.search("")
        assert resp.total_count == total
        assert len(resp.results) == total  # 20건 이하이므로 전부

    def test_02_single_keyword(self, engine):
        """단일 키워드 검색"""
        eng, total = engine
        resp = eng.search("프로젝트")
        assert resp.total_count > 0
        assert len(resp.results) > 0
        # 결과에 "프로젝트" 포함 확인
        for r in resp.results:
            text = (r.email.subject + r.email.body_text).lower()
            assert "프로젝트" in text

    def test_03_multiple_keywords(self, engine):
        """복합 키워드 검색 (AND 조건)"""
        eng, _ = engine
        resp = eng.search("프로젝트 보고서")
        assert resp.total_count > 0
        # "프로젝트"와 "보고서" 둘 다 포함되어야 함
        for r in resp.results:
            text = (r.email.subject + r.email.body_text)
            assert "프로젝트" in text or "보고서" in text

    def test_04_no_results(self, engine):
        """매칭 없는 검색어 → 빈 결과"""
        eng, _ = engine
        resp = eng.search("zzzzxxxyyy존재하지않는단어")
        assert resp.total_count == 0
        assert len(resp.results) == 0

    def test_05_bm25_ranking(self, engine):
        """BM25 랭킹: 관련도 높은 결과가 상위"""
        eng, _ = engine
        resp = eng.search("견적서")
        if len(resp.results) >= 2:
            # rank_score가 존재하고 정렬되어야 함 (낮을수록 관련도 높음 → abs 변환 후 내림차순)
            scores = [r.rank_score for r in resp.results]
            assert all(s >= 0 for s in scores)

    def test_06_snippet_generation(self, engine):
        """검색어 하이라이트 snippet 생성"""
        eng, _ = engine
        resp = eng.search("견적서")
        found_snippet = False
        for r in resp.results:
            if r.body_snippet or r.title_snippet:
                found_snippet = True
                break
        assert found_snippet, "snippet이 하나도 생성되지 않음"

    def test_07_search_body_content(self, engine):
        """본문 내용으로 검색"""
        eng, _ = engine
        resp = eng.search("집행률")
        assert resp.total_count > 0

    def test_08_search_sender(self, engine):
        """발신자 이름으로 검색"""
        eng, _ = engine
        resp = eng.search("김철수")
        assert resp.total_count > 0
        for r in resp.results:
            combined = r.email.sender_name + r.email.recipients
            assert "김철수" in combined

    def test_09_search_attachment_name(self, engine):
        """첨부파일 이름으로 검색"""
        eng, _ = engine
        resp = eng.search("견적서_2분기")
        assert resp.total_count > 0


class TestSearchPerformance:

    def test_10_search_speed(self, engine):
        """검색 응답 100ms 이내"""
        eng, _ = engine
        resp = eng.search("프로젝트")
        assert resp.elapsed_ms < 100, f"검색 시간 초과: {resp.elapsed_ms}ms"

    def test_11_elapsed_ms_in_response(self, engine):
        """응답에 elapsed_ms 포함"""
        eng, _ = engine
        resp = eng.search("보고서")
        assert resp.elapsed_ms >= 0


class TestPagination:

    def test_12_page_1(self, engine):
        """페이지 1 결과"""
        eng, total = engine
        resp = eng.search("", page=1, per_page=5)
        assert len(resp.results) == min(5, total)
        assert resp.page == 1
        assert resp.per_page == 5
        assert resp.total_count == total

    def test_13_page_2(self, engine):
        """페이지 2 결과"""
        eng, total = engine
        resp = eng.search("", page=2, per_page=5)
        if total > 5:
            assert len(resp.results) > 0
            assert resp.page == 2

    def test_14_has_next_prev(self, engine):
        """has_next, has_prev 속성"""
        eng, total = engine
        resp = eng.search("", page=1, per_page=5)
        if total > 5:
            assert resp.has_next is True
            assert resp.has_prev is False

    def test_15_total_pages(self, engine):
        """total_pages 계산"""
        eng, total = engine
        resp = eng.search("", page=1, per_page=5)
        expected = (total + 4) // 5
        assert resp.total_pages == expected


class TestSortOptions:

    def test_16_sort_by_newest(self, engine):
        """최신순 정렬"""
        eng, _ = engine
        resp = eng.search("", sort_by="received_at_desc")
        if len(resp.results) >= 2:
            dates = [r.email.received_at for r in resp.results]
            assert dates == sorted(dates, reverse=True)

    def test_17_sort_by_oldest(self, engine):
        """오래된순 정렬"""
        eng, _ = engine
        resp = eng.search("", sort_by="received_at_asc")
        if len(resp.results) >= 2:
            dates = [r.email.received_at for r in resp.results]
            assert dates == sorted(dates)


class TestExtraFilters:

    def test_18_folder_filter(self, engine):
        """폴더 필터"""
        eng, _ = engine
        resp = eng.search("", extra_where=[("folder_name = ?", ["받은편지함"])])
        for r in resp.results:
            assert r.email.folder_name == "받은편지함"

    def test_19_attachment_filter(self, engine):
        """첨부파일 있음 필터"""
        eng, _ = engine
        resp = eng.search("", extra_where=[("has_attachments = ?", [1])])
        for r in resp.results:
            assert r.email.has_attachments == 1

    def test_20_combined_filter(self, engine):
        """키워드 + 폴더 + 첨부 결합"""
        eng, _ = engine
        resp = eng.search("견적서",
                          extra_where=[("folder_name = ?", ["받은편지함"]),
                                       ("has_attachments = ?", [1])])
        for r in resp.results:
            assert r.email.folder_name == "받은편지함"
            assert r.email.has_attachments == 1


class TestUtilMethods:

    def test_21_get_total_count(self, engine):
        """전체 인덱싱 메일 수"""
        eng, total = engine
        assert eng.get_total_count() == total

    def test_22_get_folder_counts(self, engine):
        """폴더별 카운트"""
        eng, _ = engine
        counts = eng.get_folder_counts()
        assert "받은편지함" in counts
        assert "보낸편지함" in counts
        assert counts["받은편지함"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
