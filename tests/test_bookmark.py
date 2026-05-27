"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[C10] 검색어 북마크 테스트
"""

import pytest
import json
import tempfile
from pathlib import Path

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.database import init_db
from core.bookmark_manager import BookmarkManager


@pytest.fixture
def bm():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    conn = init_db(db_path)
    mgr = BookmarkManager(conn)
    yield mgr
    conn.close()
    db_path.unlink(missing_ok=True)


class TestBookmark:

    def test_01_add_bookmark(self, bm):
        """북마크 추가"""
        bid = bm.add("프로젝트 보고서", query="from:김철수 프로젝트")
        assert bid > 0
        assert bm.get_count() == 1

    def test_02_get_all(self, bm):
        """전체 북마크 조회 (position 순)"""
        bm.add("북마크1", query="q1")
        bm.add("북마크2", query="q2")
        bm.add("북마크3", query="q3")

        all_bm = bm.get_all()
        assert len(all_bm) == 3
        assert all_bm[0].name == "북마크1"

    def test_03_delete(self, bm):
        """북마크 삭제"""
        bid = bm.add("삭제용", query="delete_me")
        assert bm.get_count() == 1

        result = bm.delete(bid)
        assert result is True
        assert bm.get_count() == 0

    def test_04_update_name(self, bm):
        """북마크 이름 변경"""
        bid = bm.add("원래 이름", query="q1")
        bm.update_name(bid, "변경된 이름")

        item = bm.get_by_id(bid)
        assert item.name == "변경된 이름"

    def test_05_filters_json(self, bm):
        """필터 JSON 저장/복원"""
        filters = {"folder": "받은편지함", "has_att": True, "date": "최근 7일"}
        bid = bm.add("필터 포함", query="견적서", filters=filters)

        item = bm.get_by_id(bid)
        restored = json.loads(item.filters)
        assert restored["folder"] == "받은편지함"
        assert restored["has_att"] is True

    def test_06_is_bookmarked(self, bm):
        """북마크 여부 확인"""
        bm.add("테스트", query="특정 쿼리")
        assert bm.is_bookmarked("특정 쿼리") is True
        assert bm.is_bookmarked("없는 쿼리") is False

    def test_07_toggle_add(self, bm):
        """토글: 없으면 추가"""
        result = bm.toggle("토글 테스트")
        assert result is True  # 추가됨
        assert bm.is_bookmarked("토글 테스트") is True

    def test_08_toggle_remove(self, bm):
        """토글: 있으면 삭제"""
        bm.toggle("토글 테스트")  # 추가
        result = bm.toggle("토글 테스트")  # 삭제
        assert result is False  # 삭제됨
        assert bm.is_bookmarked("토글 테스트") is False

    def test_09_duplicate_query_allowed(self, bm):
        """같은 쿼리로 여러 북마크 가능"""
        bm.add("버전1", query="같은 쿼리", filters={"v": 1})
        bm.add("버전2", query="같은 쿼리", filters={"v": 2})
        assert bm.get_count() == 2

    def test_10_find_by_query(self, bm):
        """쿼리로 북마크 찾기"""
        bm.add("찾기 테스트", query="find_this")
        found = bm.find_by_query("find_this")
        assert found is not None
        assert found.name == "찾기 테스트"

    def test_11_position_auto_increment(self, bm):
        """position 자동 증가"""
        bm.add("A", query="a")
        bm.add("B", query="b")
        bm.add("C", query="c")

        all_bm = bm.get_all()
        positions = [b.position for b in all_bm]
        assert positions == sorted(positions)  # 오름차순


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
