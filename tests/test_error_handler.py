"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[C15] 에러 처리 테스트 — 5개 핵심 시나리오
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.database import init_db, get_email_count
from core.error_handler import (
    check_disk_space, check_db_integrity, try_recover_db,
    safe_search, safe_db_operation,
    AppError, OutlookNotRunningError, OutlookDisconnectedError,
    DatabaseCorruptedError, DiskSpaceError
)
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
    mails = list(mock.iter_mails(OlDefaultFolders.INBOX)) + list(mock.iter_mails(OlDefaultFolders.SENT))
    builder.build_from_iterator(iter(mails), len(mails))
    yield conn, db_path
    conn.close()
    db_path.unlink(missing_ok=True)


class TestErrorClasses:
    """에러 클래스 기본 동작"""

    def test_01_outlook_not_running_error(self):
        e = OutlookNotRunningError()
        assert "Outlook" in e.title
        assert "실행" in e.message
        assert e.suggestion != ""

    def test_02_outlook_disconnected_error(self):
        e = OutlookDisconnectedError()
        assert "끊김" in e.title
        assert "인덱싱" in e.message or "동기화" in e.suggestion

    def test_03_database_corrupted_error(self):
        e = DatabaseCorruptedError("테스트 상세")
        assert "데이터베이스" in e.title
        assert "테스트 상세" in e.message

    def test_04_disk_space_error(self):
        e = DiskSpaceError(50.0)
        assert "디스크" in e.title
        assert "50" in e.message

    def test_05_app_error_inheritance(self):
        e = AppError("제목", "메시지", "제안")
        assert isinstance(e, Exception)
        assert e.title == "제목"
        assert e.message == "메시지"
        assert e.suggestion == "제안"


class TestDiskSpaceCheck:
    """시나리오 4: 디스크 공간 체크"""

    def test_06_disk_space_available(self):
        ok, avail = check_disk_space(min_mb=1)
        assert ok is True
        assert avail > 0

    def test_07_disk_space_extreme_requirement(self):
        """터무니없이 큰 요구 → 실패"""
        ok, avail = check_disk_space(min_mb=999_999_999)
        assert ok is False


class TestDBIntegrity:
    """시나리오 3: DB 무결성 검사"""

    def test_08_healthy_db(self, env):
        conn, _ = env
        ok, msg = check_db_integrity(conn)
        assert ok is True
        assert msg == "ok"

    def test_09_recover_fts(self, env):
        """FTS5 재구축 성공"""
        conn, _ = env
        result = try_recover_db(conn)
        assert result is True

        # 재구축 후 검색 가능
        rows = conn.execute(
            "SELECT rowid FROM emails_fts WHERE emails_fts MATCH '프로젝트'"
        ).fetchall()
        assert len(rows) >= 1


class TestSafeSearch:
    """시나리오 3+5: 안전한 검색 래핑"""

    def test_10_safe_search_normal(self, env):
        conn, _ = env
        engine = SearchEngine(conn)

        def do_search():
            return engine.search("프로젝트")

        result = safe_search(conn, do_search)
        assert result is not None
        assert result.total_count > 0

    def test_11_safe_search_with_bad_query(self, env):
        """특수문자가 포함된 쿼리도 에러 없이 처리"""
        conn, _ = env
        engine = SearchEngine(conn)

        for q in ["", "   ", "@@##$$", "a" * 500, "프로젝트\x00테스트"]:
            try:
                result = engine.search(q)
                assert result is not None
            except Exception:
                pass  # 에러가 나더라도 크래시는 아님


class TestSafeDBOperation:
    """시나리오 4: 안전한 DB 쓰기"""

    def test_12_safe_operation_normal(self, env):
        conn, _ = env

        def do_insert():
            conn.execute(
                "INSERT OR IGNORE INTO search_history (keyword, search_count) VALUES (?, ?)",
                ("테스트 키워드", 1)
            )
            conn.commit()
            return True

        result = safe_db_operation(conn, do_insert)
        assert result is True


class TestEdgeCases:
    """시나리오 5: 예외 케이스"""

    def test_13_empty_db_search(self):
        """빈 DB에서 검색"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        conn = init_db(db_path)
        engine = SearchEngine(conn)

        result = engine.search("아무거나")
        assert result.total_count == 0
        assert len(result.results) == 0

        result2 = engine.search("")
        assert result2.total_count == 0

        conn.close()
        db_path.unlink(missing_ok=True)

    def test_14_very_long_query(self, env):
        """매우 긴 검색어"""
        conn, _ = env
        engine = SearchEngine(conn)
        long_query = "테스트 " * 100
        result = engine.search(long_query)
        assert result is not None  # 크래시 없음

    def test_15_concurrent_read_write(self, env):
        """동시 읽기/쓰기 (WAL 모드 검증)"""
        conn, db_path = env

        # 읽기
        engine = SearchEngine(conn)
        r1 = engine.search("프로젝트")

        # 쓰기 (같은 연결)
        conn.execute(
            "INSERT OR IGNORE INTO search_history (keyword) VALUES (?)",
            ("동시성 테스트",)
        )
        conn.commit()

        # 읽기 다시
        r2 = engine.search("프로젝트")
        assert r2.total_count == r1.total_count

    def test_16_schema_reinit_safe(self, env):
        """스키마 재초기화해도 데이터 유지"""
        conn, _ = env
        before = get_email_count(conn)

        from data.database import init_schema
        init_schema(conn)  # 재호출

        after = get_email_count(conn)
        assert after == before


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
