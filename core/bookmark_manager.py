"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[M08] 검색어 북마크 관리

자주 사용하는 검색어+필터 조합을 저장하여 원클릭 재검색.
"""

import sqlite3
import json
import logging
from typing import List, Optional

from data.models import Bookmark

logger = logging.getLogger(__name__)


class BookmarkManager:
    """
    검색어 북마크 CRUD

    사용법:
        bm = BookmarkManager(db_conn)
        bm.add("프로젝트 보고서", query="from:김철수 프로젝트", filters={"folder": "받은편지함"})
        bookmarks = bm.get_all()
        bm.delete(bookmark_id)
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, name: str, query: str, filters: dict = None) -> int:
        """
        북마크 추가.

        Args:
            name: 표시 이름 (기본: 검색어 그대로)
            query: 검색어 문자열
            filters: 필터 상태 dict (JSON으로 저장)

        Returns:
            생성된 북마크 ID
        """
        if not name:
            name = query or "새 북마크"

        filters_json = json.dumps(filters or {}, ensure_ascii=False)

        # 최대 position 구하기
        row = self.conn.execute("SELECT MAX(position) as max_pos FROM bookmarks").fetchone()
        next_pos = (row["max_pos"] or 0) + 1

        try:
            cursor = self.conn.execute(
                "INSERT INTO bookmarks (name, query, filters, position) VALUES (?, ?, ?, ?)",
                (name, query, filters_json, next_pos)
            )
            self.conn.commit()
            bookmark_id = cursor.lastrowid
            logger.info(f"북마크 추가: '{name}' (ID={bookmark_id})")
            return bookmark_id
        except Exception as e:
            logger.error(f"북마크 추가 실패: {e}")
            return -1

    def get_all(self) -> List[Bookmark]:
        """전체 북마크 목록 (position 순)"""
        try:
            rows = self.conn.execute(
                "SELECT * FROM bookmarks ORDER BY position ASC, created_at DESC"
            ).fetchall()
            return [Bookmark.from_row(r) for r in rows]
        except Exception as e:
            logger.error(f"북마크 조회 실패: {e}")
            return []

    def get_by_id(self, bookmark_id: int) -> Optional[Bookmark]:
        """ID로 북마크 조회"""
        try:
            row = self.conn.execute(
                "SELECT * FROM bookmarks WHERE id = ?", (bookmark_id,)
            ).fetchone()
            return Bookmark.from_row(row) if row else None
        except Exception:
            return None

    def delete(self, bookmark_id: int) -> bool:
        """북마크 삭제"""
        try:
            self.conn.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,))
            self.conn.commit()
            logger.info(f"북마크 삭제: ID={bookmark_id}")
            return True
        except Exception as e:
            logger.error(f"북마크 삭제 실패: {e}")
            return False

    def update_name(self, bookmark_id: int, new_name: str) -> bool:
        """북마크 이름 변경"""
        try:
            self.conn.execute(
                "UPDATE bookmarks SET name = ? WHERE id = ?",
                (new_name, bookmark_id)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"북마크 이름 변경 실패: {e}")
            return False

    def update_position(self, bookmark_id: int, new_position: int) -> bool:
        """북마크 순서 변경"""
        try:
            self.conn.execute(
                "UPDATE bookmarks SET position = ? WHERE id = ?",
                (new_position, bookmark_id)
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    def is_bookmarked(self, query: str) -> bool:
        """해당 검색어가 북마크되어 있는지 확인"""
        row = self.conn.execute(
            "SELECT 1 FROM bookmarks WHERE query = ?", (query,)
        ).fetchone()
        return row is not None

    def find_by_query(self, query: str) -> Optional[Bookmark]:
        """검색어로 북마크 찾기"""
        try:
            row = self.conn.execute(
                "SELECT * FROM bookmarks WHERE query = ?", (query,)
            ).fetchone()
            return Bookmark.from_row(row) if row else None
        except Exception:
            return None

    def toggle(self, query: str, filters: dict = None) -> bool:
        """
        북마크 토글: 있으면 삭제, 없으면 추가.

        Returns:
            True = 추가됨, False = 삭제됨
        """
        existing = self.find_by_query(query)
        if existing:
            self.delete(existing.id)
            return False
        else:
            self.add(name=query, query=query, filters=filters)
            return True

    def get_count(self) -> int:
        """북마크 총 개수"""
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM bookmarks").fetchone()
        return row["cnt"] if row else 0
