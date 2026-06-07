"""
OutLook AnyFinder Ver0.9.1.1 for SESUNG Team
[M07] 자동완성 엔진

검색 히스토리 기반 자동완성.
사용자가 타이핑할 때 이전에 검색했던 키워드를 빈도순으로 제안합니다.
"""

import sqlite3
import logging
from typing import List
from datetime import datetime

from data.models import SearchHistoryItem

logger = logging.getLogger(__name__)


class AutocompleteEngine:
    """
    검색어 자동완성 엔진

    사용법:
        ac = AutocompleteEngine(db_conn)
        ac.record_search("프로젝트 보고서")      # 검색 기록
        suggestions = ac.get_suggestions("프로")  # 자동완성 후보
    """

    MAX_SUGGESTIONS = 8

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def record_search(self, keyword: str):
        """
        검색어를 히스토리에 기록.
        이미 있으면 search_count 증가 + 시간 갱신.
        """
        keyword = keyword.strip()
        if not keyword or len(keyword) < 2:
            return

        try:
            existing = self.conn.execute(
                "SELECT id, search_count FROM search_history WHERE keyword = ?",
                (keyword,)
            ).fetchone()

            now = datetime.now().isoformat()[:19]

            if existing:
                self.conn.execute(
                    "UPDATE search_history SET search_count = search_count + 1, last_searched_at = ? WHERE id = ?",
                    (now, existing["id"])
                )
            else:
                self.conn.execute(
                    "INSERT INTO search_history (keyword, search_count, last_searched_at, created_at) VALUES (?, 1, ?, ?)",
                    (keyword, now, now)
                )
            self.conn.commit()
        except Exception as e:
            logger.error(f"검색 히스토리 기록 실패: {e}")

    def get_suggestions(self, prefix: str, limit: int = None) -> List[SearchHistoryItem]:
        """
        접두사로 시작하는 검색어 후보를 빈도순으로 반환.

        Args:
            prefix: 사용자가 입력 중인 문자열
            limit: 최대 후보 수 (기본 MAX_SUGGESTIONS=8)

        Returns:
            List[SearchHistoryItem]: 빈도 높은 순
        """
        if not prefix or len(prefix) < 1:
            return self.get_recent(limit)

        limit = limit or self.MAX_SUGGESTIONS

        try:
            rows = self.conn.execute(
                """
                SELECT id, keyword, search_count, last_searched_at
                FROM search_history
                WHERE keyword LIKE ?
                ORDER BY search_count DESC, last_searched_at DESC
                LIMIT ?
                """,
                (f"{prefix}%", limit)
            ).fetchall()

            return [SearchHistoryItem.from_row(r) for r in rows]
        except Exception as e:
            logger.error(f"자동완성 조회 실패: {e}")
            return []

    def get_recent(self, limit: int = None) -> List[SearchHistoryItem]:
        """최근 검색어 반환 (접두사 없을 때)"""
        limit = limit or self.MAX_SUGGESTIONS
        try:
            rows = self.conn.execute(
                """
                SELECT id, keyword, search_count, last_searched_at
                FROM search_history
                ORDER BY last_searched_at DESC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()
            return [SearchHistoryItem.from_row(r) for r in rows]
        except Exception:
            return []

    def delete_item(self, keyword: str):
        """개별 히스토리 삭제"""
        try:
            self.conn.execute("DELETE FROM search_history WHERE keyword = ?", (keyword,))
            self.conn.commit()
        except Exception as e:
            logger.error(f"히스토리 삭제 실패: {e}")

    def clear_all(self):
        """전체 히스토리 초기화"""
        try:
            self.conn.execute("DELETE FROM search_history")
            self.conn.commit()
        except Exception as e:
            logger.error(f"히스토리 초기화 실패: {e}")

    def get_count(self) -> int:
        """히스토리 총 개수"""
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM search_history").fetchone()
        return row["cnt"] if row else 0
