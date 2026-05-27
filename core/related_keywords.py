"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[M09] 추천 연관 검색어 엔진

3가지 소스에서 연관 키워드를 추출하여 검색창 하단에 제안합니다.
1. 정적 연관어 사전 (수동 등록)
2. 검색 세션 기반 (같은 세션에서 검색된 키워드)
3. 동시 출현 분석 (같은 메일에 자주 등장하는 단어)
"""

import sqlite3
import uuid
import logging
from typing import List, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class RelatedKeywordsEngine:
    """
    연관 검색어 추천 엔진

    사용법:
        rk = RelatedKeywordsEngine(db_conn)
        rk.record_session("프로젝트")       # 세션에 검색 기록
        related = rk.get_related("견적서")  # 연관 키워드 추천
    """

    MAX_RELATED = 6
    SESSION_TIMEOUT_MINUTES = 5  # 같은 세션으로 간주하는 시간

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._current_session_id = str(uuid.uuid4())[:8]
        self._last_search_time = datetime.now()

    def record_session(self, keyword: str):
        """검색 키워드를 현재 세션에 기록"""
        keyword = keyword.strip()
        if not keyword or len(keyword) < 2:
            return

        now = datetime.now()

        # 세션 타임아웃 체크 → 새 세션 생성
        if (now - self._last_search_time).seconds > self.SESSION_TIMEOUT_MINUTES * 60:
            self._current_session_id = str(uuid.uuid4())[:8]

        self._last_search_time = now

        try:
            self.conn.execute(
                "INSERT INTO search_sessions (session_id, keyword, searched_at) VALUES (?, ?, ?)",
                (self._current_session_id, keyword, now.isoformat()[:19])
            )
            self.conn.commit()
        except Exception as e:
            logger.debug(f"세션 기록 실패: {e}")

    def get_related(self, keyword: str, limit: int = None) -> List[str]:
        """
        연관 키워드 추천 (3가지 소스 병합)

        Args:
            keyword: 현재 검색어
            limit: 최대 추천 수

        Returns:
            List[str]: 연관 키워드 리스트 (점수순)
        """
        if not keyword or len(keyword) < 2:
            return []

        limit = limit or self.MAX_RELATED
        scored = {}  # keyword → score

        # 1. 정적 연관어 사전
        try:
            rows = self.conn.execute(
                "SELECT related, score FROM related_keywords WHERE keyword = ? ORDER BY score DESC LIMIT ?",
                (keyword, limit * 2)
            ).fetchall()
            for r in rows:
                w = r["related"]
                if w != keyword:
                    scored[w] = scored.get(w, 0) + r["score"] * 3  # 가중치 3배
        except Exception:
            pass

        # 2. 세션 기반 연관 (같은 세션에서 검색된 다른 키워드)
        try:
            rows = self.conn.execute(
                """
                SELECT ss2.keyword, COUNT(*) as cnt
                FROM search_sessions ss1
                JOIN search_sessions ss2 ON ss1.session_id = ss2.session_id
                WHERE ss1.keyword = ? AND ss2.keyword != ?
                GROUP BY ss2.keyword
                ORDER BY cnt DESC
                LIMIT ?
                """,
                (keyword, keyword, limit * 2)
            ).fetchall()
            for r in rows:
                w = r["keyword"]
                scored[w] = scored.get(w, 0) + r["cnt"] * 2  # 가중치 2배
        except Exception:
            pass

        # 3. 검색 히스토리에서 유사 키워드 (접두사 공유)
        try:
            if len(keyword) >= 2:
                prefix = keyword[:2]
                rows = self.conn.execute(
                    """
                    SELECT keyword, search_count
                    FROM search_history
                    WHERE keyword LIKE ? AND keyword != ?
                    ORDER BY search_count DESC
                    LIMIT ?
                    """,
                    (f"{prefix}%", keyword, limit)
                ).fetchall()
                for r in rows:
                    w = r["keyword"]
                    scored[w] = scored.get(w, 0) + r["search_count"]
        except Exception:
            pass

        # 점수순 정렬 → 상위 N개
        sorted_keywords = sorted(scored.items(), key=lambda x: x[1], reverse=True)
        return [kw for kw, _ in sorted_keywords[:limit]]

    def add_static_relation(self, keyword: str, related: str, score: float = 1.0):
        """정적 연관어 수동 등록"""
        try:
            self.conn.execute(
                """
                INSERT INTO related_keywords (keyword, related, score, source)
                VALUES (?, ?, ?, 'manual')
                ON CONFLICT(keyword, related) DO UPDATE SET score = ?
                """,
                (keyword, related, score, score)
            )
            self.conn.commit()
        except Exception as e:
            logger.debug(f"연관어 등록 실패: {e}")

    def add_bulk_relations(self, relations: List[Tuple[str, str, float]]):
        """연관어 일괄 등록 [(keyword, related, score), ...]"""
        try:
            self.conn.executemany(
                """
                INSERT OR IGNORE INTO related_keywords (keyword, related, score, source)
                VALUES (?, ?, ?, 'manual')
                """,
                relations
            )
            self.conn.commit()
        except Exception as e:
            logger.debug(f"연관어 일괄 등록 실패: {e}")

    def seed_default_relations(self):
        """기본 연관어 사전 시드"""
        defaults = [
            ("견적서", "견적", 2.0), ("견적서", "단가표", 1.5), ("견적서", "가격표", 1.5),
            ("견적서", "예산", 1.0), ("견적서", "계약서", 1.0),
            ("보고서", "보고", 2.0), ("보고서", "리포트", 1.5), ("보고서", "현황", 1.0),
            ("프로젝트", "사업", 1.5), ("프로젝트", "과제", 1.0), ("프로젝트", "일정", 1.0),
            ("회의", "미팅", 2.0), ("회의", "회의록", 1.5), ("회의", "안건", 1.0),
            ("예산", "비용", 1.5), ("예산", "집행", 1.0), ("예산", "결산", 1.0),
            ("인사", "발령", 1.5), ("인사", "채용", 1.0), ("인사", "평가", 1.0),
            ("출장", "출장보고", 1.5), ("출장", "교통비", 1.0),
            ("계약", "계약서", 2.0), ("계약", "견적서", 1.0), ("계약", "납품", 1.0),
        ]
        self.add_bulk_relations(defaults)
