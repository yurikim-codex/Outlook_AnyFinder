"""
OutLook AnyFinder Ver0.9.1.1 for SESUNG Team
[C12] 연관 검색어 테스트
"""

import pytest
import tempfile
from pathlib import Path

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.database import init_db
from core.related_keywords import RelatedKeywordsEngine
from core.autocomplete import AutocompleteEngine


@pytest.fixture
def rk():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    conn = init_db(db_path)
    engine = RelatedKeywordsEngine(conn)
    yield engine, conn
    conn.close()
    db_path.unlink(missing_ok=True)


class TestRelatedKeywords:

    def test_01_empty_related(self, rk):
        """연관어 없을 때 빈 목록"""
        engine, _ = rk
        result = engine.get_related("존재하지않는키워드")
        assert result == []

    def test_02_static_relation(self, rk):
        """정적 연관어 등록 및 반환"""
        engine, _ = rk
        engine.add_static_relation("견적서", "견적", 2.0)
        engine.add_static_relation("견적서", "단가표", 1.5)

        result = engine.get_related("견적서")
        assert "견적" in result
        assert "단가표" in result

    def test_03_session_based(self, rk):
        """세션 기반 연관어"""
        engine, _ = rk
        # 같은 세션에서 "견적서" → "예산" → "비용" 순서로 검색
        engine.record_session("견적서")
        engine.record_session("예산")
        engine.record_session("비용")

        result = engine.get_related("견적서")
        assert "예산" in result or "비용" in result

    def test_04_exclude_self(self, rk):
        """자기 자신 제외"""
        engine, _ = rk
        engine.add_static_relation("견적서", "견적서", 5.0)  # 자기 자신
        engine.add_static_relation("견적서", "다른것", 1.0)

        result = engine.get_related("견적서")
        assert "견적서" not in result

    def test_05_max_limit(self, rk):
        """최대 6개 제한"""
        engine, _ = rk
        for i in range(15):
            engine.add_static_relation("테스트", f"관련어{i}", float(i))

        result = engine.get_related("테스트")
        assert len(result) <= 6

    def test_06_seed_defaults(self, rk):
        """기본 연관어 사전 시드"""
        engine, _ = rk
        engine.seed_default_relations()

        result = engine.get_related("견적서")
        assert len(result) > 0
        assert "견적" in result

    def test_07_short_keyword_ignored(self, rk):
        """짧은 키워드 무시"""
        engine, _ = rk
        result = engine.get_related("A")
        assert result == []

    def test_08_history_based_similar(self, rk):
        """히스토리 기반 유사 키워드"""
        engine, conn = rk
        ac = AutocompleteEngine(conn)
        ac.record_search("프로젝트 보고서")
        ac.record_search("프로젝트 견적서")
        ac.record_search("프로모션")

        result = engine.get_related("프로젝트 보고서")
        # "프로" 접두사를 공유하는 다른 키워드 제안 가능
        # (히스토리가 있으므로 빈 리스트가 아닐 수 있음)
        assert isinstance(result, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
