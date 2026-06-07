"""
OutLook AnyFinder Ver0.9.1.1 for SESUNG Team
[C09] 자동완성 테스트
"""

import pytest
import tempfile
from pathlib import Path

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.database import init_db
from core.autocomplete import AutocompleteEngine


@pytest.fixture
def ac():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    conn = init_db(db_path)
    engine = AutocompleteEngine(conn)
    yield engine
    conn.close()
    db_path.unlink(missing_ok=True)


class TestAutocomplete:

    def test_01_empty_history(self, ac):
        """히스토리 비어있을 때 빈 목록"""
        result = ac.get_suggestions("프로")
        assert result == []

    def test_02_record_and_retrieve(self, ac):
        """검색 기록 추가 후 조회"""
        ac.record_search("프로젝트 보고서")
        result = ac.get_suggestions("프로")
        assert len(result) == 1
        assert result[0].keyword == "프로젝트 보고서"
        assert result[0].search_count == 1

    def test_03_count_increment(self, ac):
        """동일 키워드 재검색 시 횟수 증가"""
        ac.record_search("프로젝트")
        ac.record_search("프로젝트")
        ac.record_search("프로젝트")
        result = ac.get_suggestions("프로")
        assert result[0].search_count == 3

    def test_04_prefix_matching(self, ac):
        """접두사 매칭"""
        ac.record_search("프로젝트 보고서")
        ac.record_search("프로젝트 견적서")
        ac.record_search("프로모션 계획")
        ac.record_search("마케팅 보고서")  # "프로"에 매칭 안 됨

        result = ac.get_suggestions("프로")
        assert len(result) == 3
        keywords = [r.keyword for r in result]
        assert "마케팅 보고서" not in keywords

    def test_05_frequency_order(self, ac):
        """빈도순 정렬: 많이 검색한 것이 상위"""
        ac.record_search("프로젝트 보고서")
        for _ in range(5):
            ac.record_search("프로젝트 견적서")
        for _ in range(2):
            ac.record_search("프로모션")

        result = ac.get_suggestions("프로")
        assert result[0].keyword == "프로젝트 견적서"  # 5회
        assert result[1].keyword == "프로모션"          # 2회

    def test_06_max_limit(self, ac):
        """최대 8개 제한"""
        for i in range(15):
            ac.record_search(f"프로 테스트 {i}")

        result = ac.get_suggestions("프로")
        assert len(result) <= 8

    def test_07_delete_item(self, ac):
        """개별 히스토리 삭제"""
        ac.record_search("삭제할 키워드")
        ac.record_search("유지할 키워드")

        ac.delete_item("삭제할 키워드")

        result = ac.get_suggestions("삭")
        assert len(result) == 0
        result2 = ac.get_suggestions("유")
        assert len(result2) == 1

    def test_08_clear_all(self, ac):
        """전체 히스토리 초기화"""
        ac.record_search("키워드1")
        ac.record_search("키워드2")
        ac.record_search("키워드3")
        assert ac.get_count() == 3

        ac.clear_all()
        assert ac.get_count() == 0

    def test_09_short_keyword_ignored(self, ac):
        """1글자 미만 검색어는 기록 안 됨"""
        ac.record_search("")
        ac.record_search("A")
        assert ac.get_count() == 0

    def test_10_get_recent(self, ac):
        """최근 검색어 (접두사 없이)"""
        ac.record_search("최근 검색 1")
        ac.record_search("최근 검색 2")
        ac.record_search("최근 검색 3")

        result = ac.get_recent(limit=2)
        assert len(result) == 2

    def test_11_custom_limit(self, ac):
        """커스텀 limit"""
        for i in range(10):
            ac.record_search(f"테스트 {i}")

        result = ac.get_suggestions("테스트", limit=3)
        assert len(result) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
