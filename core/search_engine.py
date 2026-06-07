"""
OutLook AnyFinder Ver0.9.1.1 for SESUNG Team
[M04] 검색 엔진

FTS5 전문검색 실행, BM25 랭킹, snippet 하이라이트, 페이지네이션
query_parser와 연동하여 자연어 검색을 지원합니다.
"""

import sqlite3
import time
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass

from data.models import EmailRecord, SearchResult
from core.query_parser import parse_query, build_search_sql, build_count_sql, ParsedQuery

logger = logging.getLogger(__name__)


@dataclass
class SearchResponse:
    """검색 응답 전체"""
    results: List[SearchResult]
    total_count: int
    page: int
    per_page: int
    elapsed_ms: float
    query: str
    parsed: Optional[ParsedQuery] = None

    @property
    def total_pages(self) -> int:
        if self.per_page <= 0:
            return 0
        return max(1, (self.total_count + self.per_page - 1) // self.per_page)

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        return self.page > 1


class SearchEngine:
    """
    메일 검색 엔진

    사용법:
        engine = SearchEngine(db_conn)
        response = engine.search("프로젝트 보고서")
        for r in response.results:
            print(r.email.subject, r.rank_score, r.body_snippet)
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def search(self, query: str, page: int = 1, per_page: int = 20,
               sort_by: str = "rank",
               extra_where: List[Tuple[str, list]] = None,
               search_columns: List[str] = None,
               match_operator: str = "AND",
               contains_search: bool = False) -> SearchResponse:
        """
        메일 검색 실행

        Args:
            query: 사용자 검색어 (자연어)
            page: 페이지 번호 (1부터)
            per_page: 페이지당 결과 수
            sort_by: "rank" | "received_at_desc" | "received_at_asc"
            extra_where: 추가 WHERE 절 [(clause, [params]), ...]
            search_columns: 일반 키워드를 검색할 FTS 컬럼 목록. None이면 전체 검색
            match_operator: 토큰 결합 방식("AND" 또는 "OR")

        Returns:
            SearchResponse
        """
        start = time.perf_counter()

        # 1. 쿼리 파싱
        parsed = parse_query(
            query,
            search_columns=search_columns,
            match_operator=match_operator,
            contains_search=contains_search,
        )
        parsed.sort_by = sort_by

        # 추가 필터 (UI 필터 칩에서 전달)
        if extra_where:
            for clause, params in extra_where:
                parsed.where_clauses.append(clause)
                parsed.where_params.extend(params)

        # 2. 검색 SQL 생성
        search_sql, search_params = build_search_sql(parsed, page, per_page)

        # 3. 검색 실행
        results = []
        try:
            rows = self.conn.execute(search_sql, search_params).fetchall()
            for row in rows:
                email = EmailRecord.from_row(row)
                sr = SearchResult(
                    email=email,
                    rank_score=abs(row["rank_score"]) if row["rank_score"] else 0,
                    title_snippet=row["title_snippet"] or "",
                    body_snippet=row["body_snippet"] or "",
                )
                results.append(sr)
        except Exception as e:
            logger.error(f"검색 실행 오류: {e} | SQL: {search_sql} | params: {search_params}")

        # 4. 총 건수 쿼리
        total_count = 0
        try:
            count_sql, count_params = build_count_sql(parsed)
            row = self.conn.execute(count_sql, count_params).fetchone()
            total_count = row["cnt"] if row else 0
        except Exception as e:
            logger.error(f"카운트 쿼리 오류: {e}")

        elapsed_ms = (time.perf_counter() - start) * 1000

        logger.debug(
            f"검색 완료: '{query}' → {len(results)}건/{total_count}건 "
            f"({elapsed_ms:.1f}ms) page={page}"
        )

        return SearchResponse(
            results=results,
            total_count=total_count,
            page=page,
            per_page=per_page,
            elapsed_ms=round(elapsed_ms, 1),
            query=query,
            parsed=parsed,
        )

    def search_all(self, query: str, sort_by: str = "rank",
                    extra_where: List[Tuple[str, list]] = None,
                    search_columns: List[str] = None,
                    match_operator: str = "AND",
                    contains_search: bool = False) -> SearchResponse:
        """전체 결과 반환 (페이지네이션 없음, 최대 1000건)"""
        return self.search(query, page=1, per_page=1000, sort_by=sort_by,
                          extra_where=extra_where, search_columns=search_columns,
                          match_operator=match_operator,
                          contains_search=contains_search)

    def get_total_count(self) -> int:
        """전체 인덱싱된 메일 수"""
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM emails").fetchone()
        return row["cnt"] if row else 0

    def get_folder_counts(self) -> dict:
        """폴더별 메일 수"""
        rows = self.conn.execute(
            "SELECT folder_name, COUNT(*) as cnt FROM emails GROUP BY folder_name ORDER BY cnt DESC"
        ).fetchall()
        return {row["folder_name"]: row["cnt"] for row in rows}
