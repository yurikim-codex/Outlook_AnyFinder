"""
OutLook AnyFinder Ver0.9.1.1 for SESUNG Team
[M05] 자연어 → FTS5 쿼리 변환

사용자 입력을 FTS5 MATCH 쿼리와 SQL WHERE 절로 분리 파싱합니다.

지원 구문:
    프로젝트 보고서          → FTS5: 프로젝트 AND 보고서
    from:김철수              → FTS5: sender_name:김철수
    to:이영희                → FTS5: recipients:이영희
    subject:견적서           → FTS5: subject:견적서
    attachment:xlsx          → WHERE: attachment_types LIKE '%xlsx%'
    첨부:pdf                 → WHERE: attachment_types LIKE '%pdf%'
    폴더:받은편지함           → WHERE: folder_name = '받은편지함'
    날짜:2026-05             → WHERE: received_at LIKE '2026-05%'
    -반려                    → FTS5: NOT 반려
    "정확한 구문"             → FTS5: "정확한 구문"
    중요:높음                 → WHERE: importance = 2
    읽음:안읽음               → WHERE: is_read = 0
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


@dataclass
class ParsedQuery:
    """파싱된 쿼리 결과"""
    fts_query: str = ""              # FTS5 MATCH 쿼리 문자열
    where_clauses: List[str] = field(default_factory=list)  # SQL WHERE 절 리스트
    where_params: List = field(default_factory=list)        # WHERE 절 파라미터
    sort_by: str = "rank"            # "rank" | "received_at_desc" | "received_at_asc"
    is_empty: bool = True            # 검색어가 비어있는지

    def build_where_sql(self) -> str:
        """WHERE 절 SQL 문자열 생성"""
        if not self.where_clauses:
            return ""
        return " AND ".join(self.where_clauses)


# ── 접두사 매핑 ──
PREFIX_MAP = {
    "from:":       "sender_name",
    "발신:":       "sender_name",
    "보낸사람:":    "sender_name",
    "to:":         "recipients",
    "받는사람:":    "recipients",
    "수신:":       "recipients",
    "subject:":    "subject",
    "제목:":       "subject",
    "attachment_name:": "attachment_names",
    "attachment_names:": "attachment_names",
    "첨부파일:":    "attachment_names",
    "첨부파일명:":  "attachment_names",
    "cc:":         "recipients",  # CC도 수신자로 검색
}

# SQL WHERE로 처리하는 접두사
FILTER_PREFIX_MAP = {
    "attachment:": "attachment_types",
    "첨부:":       "attachment_types",
    "폴더:":       "folder_name",
    "folder:":     "folder_name",
    "날짜:":       "received_at",
    "date:":       "received_at",
}

IMPORTANCE_MAP = {
    "높음": 2, "high": 2,
    "보통": 1, "normal": 1,
    "낮음": 0, "low": 0,
}

READ_MAP = {
    "안읽음": 0, "unread": 0, "미읽음": 0,
    "읽음": 1, "read": 1,
}


def parse_query(raw_input: str, search_columns: Optional[List[str]] = None,
                match_operator: str = "AND", contains_search: bool = False) -> ParsedQuery:
    """
    사용자 검색어를 파싱하여 ParsedQuery 반환

    Args:
        raw_input: 사용자가 입력한 검색 문자열
        search_columns: 일반 키워드를 제한할 FTS 컬럼 목록.
            예: ["subject"], ["attachment_names"], None=전체 FTS 컬럼
        match_operator: 일반 토큰 결합 방식. "AND" 또는 "OR"
        contains_search: True이면 일반 검색어를 FTS 단어검색 대신 LIKE 포함검색으로 처리

    Returns:
        ParsedQuery: FTS5 쿼리 + WHERE 절
    """
    result = ParsedQuery()

    if not raw_input or not raw_input.strip():
        result.is_empty = True
        return result

    raw = raw_input.strip()
    result.is_empty = False

    fts_parts = []
    tokens = _tokenize(raw)
    search_columns = [c for c in (search_columns or []) if c]
    joiner = " OR " if str(match_operator).upper() == "OR" else " AND "

    for token in tokens:
        handled = False

        # ── 1. FTS5 컬럼 접두사 (from:, to:, subject: 등)
        for prefix, fts_col in PREFIX_MAP.items():
            if token.lower().startswith(prefix):
                value = token[len(prefix):]
                if value:
                    # subject:바이오+견적서 같은 컬럼 지정 멀티 검색도 지원
                    if "+" in value:
                        for part in value.split("+"):
                            escaped = _escape_fts(part)
                            if escaped:
                                if contains_search:
                                    _add_contains_clause(result, escaped, [fts_col])
                                else:
                                    fts_parts.append(f"{fts_col}:{escaped}")
                    else:
                        escaped = _escape_fts(value)
                        if escaped:
                            if contains_search:
                                _add_contains_clause(result, escaped, [fts_col])
                            else:
                                fts_parts.append(f"{fts_col}:{escaped}")
                handled = True
                break

        if handled:
            continue

        # ── 2. SQL WHERE 필터 접두사 (attachment:, 폴더:, 날짜: 등)
        for prefix, column in FILTER_PREFIX_MAP.items():
            if token.lower().startswith(prefix):
                value = token[len(prefix):]
                if value:
                    if column == "folder_name":
                        result.where_clauses.append(f"{column} = ?")
                        result.where_params.append(value)
                    elif column == "received_at":
                        result.where_clauses.append(f"{column} LIKE ?")
                        result.where_params.append(f"{value}%")
                    elif column == "attachment_types":
                        result.where_clauses.append(f"{column} LIKE ?")
                        result.where_params.append(f"%{value}%")
                handled = True
                break

        if handled:
            continue

        # ── 3. 중요도 필터
        if token.lower().startswith("중요:") or token.lower().startswith("importance:"):
            prefix_len = 3 if token.startswith("중요") else 11
            value = token[prefix_len:]
            imp = IMPORTANCE_MAP.get(value.lower())
            if imp is not None:
                result.where_clauses.append("importance = ?")
                result.where_params.append(imp)
            continue

        # ── 4. 읽음 상태 필터
        if token.lower().startswith("읽음:") or token.lower().startswith("read:"):
            prefix_len = 3 if token.startswith("읽음") else 5
            value = token[prefix_len:]
            read_val = READ_MAP.get(value.lower())
            if read_val is not None:
                result.where_clauses.append("is_read = ?")
                result.where_params.append(read_val)
            continue

        # ── 5. 메일 주소 검색 (FTS 토크나이저/특수문자 이슈를 피하기 위해 LIKE 필터 사용)
        if _looks_like_email(token):
            result.where_clauses.append("(e.sender_email LIKE ? OR e.recipients LIKE ? OR e.cc LIKE ?)")
            like = f"%{token}%"
            result.where_params.extend([like, like, like])
            continue

        # ── 6. 제외어 (-반려)
        if token.startswith("-") and len(token) > 1:
            fts_parts.append(f"NOT {_escape_fts(token[1:])}")
            continue

        # ── 7. 구문 검색 ("정확한 구문")
        if token.startswith('"') and token.endswith('"') and len(token) > 2:
            fts_parts.append(_apply_column_scope(token, search_columns))  # 따옴표 유지
            continue

        # ── 8. + 멀티 검색
        # 예: "바이오+견적서" → "바이오" AND "견적서"가 모두 포함된 메일 검색
        # 이메일 주소의 +는 위의 메일 주소 검색에서 먼저 처리되므로 여기서는 일반 단어만 분리한다.
        if "+" in token:
            for part in token.split("+"):
                escaped = _escape_fts(part)
                if escaped:
                    if contains_search:
                        _add_contains_clause(result, escaped, search_columns)
                    else:
                        fts_parts.append(_apply_column_scope(escaped, search_columns))
            continue

        # ── 9. 일반 키워드
        escaped = _escape_fts(token)
        if escaped:
            if contains_search:
                _add_contains_clause(result, escaped, search_columns)
            else:
                fts_parts.append(_apply_column_scope(escaped, search_columns))

    # FTS 쿼리 조합
    if fts_parts:
        result.fts_query = joiner.join(fts_parts)

    return result


def _tokenize(raw: str) -> List[str]:
    """
    검색 문자열을 토큰으로 분리.
    따옴표로 감싼 구문은 하나의 토큰으로 유지.
    """
    tokens = []
    i = 0
    current = ""

    while i < len(raw):
        ch = raw[i]

        if ch == '"':
            # 따옴표 구문 — 닫는 따옴표까지
            if current.strip():
                tokens.append(current.strip())
                current = ""
            j = raw.find('"', i + 1)
            if j == -1:
                j = len(raw) - 1
            tokens.append(raw[i:j + 1])
            i = j + 1
            continue

        if ch == ' ':
            if current.strip():
                tokens.append(current.strip())
                current = ""
        else:
            current += ch

        i += 1

    if current.strip():
        tokens.append(current.strip())

    return tokens


def _add_contains_clause(result: ParsedQuery, value: str, columns: Optional[List[str]] = None):
    """검색단어포함 옵션용 LIKE 조건 추가."""
    value = (value or "").strip()
    if not value:
        return
    cols = columns or [
        "subject", "sender_name", "sender_email", "recipients", "cc",
        "body_text", "attachment_names", "categories"
    ]
    clause = "(" + " OR ".join(f"e.{c} LIKE ?" for c in cols) + ")"
    result.where_clauses.append(clause)
    result.where_params.extend([f"%{value}%"] * len(cols))


def _looks_like_email(text: str) -> bool:
    return bool(re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]*", text or ""))


def _apply_column_scope(term: str, search_columns: List[str]) -> str:
    """일반 검색어를 지정된 FTS 컬럼으로 제한한다."""
    if not search_columns:
        return term
    if len(search_columns) == 1:
        return f"{search_columns[0]}:{term}"
    # FTS5는 OR/괄호를 지원하므로 여러 컬럼 중 하나에 매칭되도록 묶는다.
    return "(" + " OR ".join(f"{col}:{term}" for col in search_columns) + ")"


def _escape_fts(text: str) -> str:
    """FTS5 특수문자 이스케이프"""
    if not text:
        return ""
    # FTS5 메타문자 제거: *, ", AND, OR, NOT, NEAR, (, )
    # 단, 사용자가 직접 입력한 것은 유지 (NOT, 따옴표 등은 상위에서 처리)
    cleaned = re.sub(r'[^\w\s가-힣ㄱ-ㅎㅏ-ㅣ@.\-]', '', text, flags=re.UNICODE)
    return cleaned.strip()



def _and_clause(clause: str) -> str:
    """WHERE clause에 테이블 별칭을 안전하게 붙인다."""
    stripped = clause.strip()
    if stripped.startswith("(") or stripped.startswith("e."):
        return f" AND {stripped}"
    return f" AND e.{stripped}"

def build_search_sql(parsed: ParsedQuery, page: int = 1, per_page: int = 20) -> Tuple[str, list]:
    """
    ParsedQuery로부터 최종 SELECT SQL 생성

    Returns:
        (sql_string, params_list)
    """
    params = []

    if parsed.fts_query:
        # FTS5 검색 + JOIN
        sql = """
            SELECT
                e.*,
                bm25(emails_fts, 10.0, 5.0, 3.0, 3.0, 1.0, 2.0, 1.0) AS rank_score,
                snippet(emails_fts, 0, '<mark>', '</mark>', '...', 20) AS title_snippet,
                snippet(emails_fts, 4, '<mark>', '</mark>', '...', 40) AS body_snippet
            FROM emails_fts
            JOIN emails e ON e.id = emails_fts.rowid
            WHERE emails_fts MATCH ?
        """
        params.append(parsed.fts_query)

        # 추가 WHERE 절
        if parsed.where_clauses:
            for clause in parsed.where_clauses:
                sql += _and_clause(clause)
            params.extend(parsed.where_params)

        # 정렬
        if parsed.sort_by == "received_at_desc":
            sql += " ORDER BY e.received_at DESC"
        elif parsed.sort_by == "received_at_asc":
            sql += " ORDER BY e.received_at ASC"
        else:
            sql += " ORDER BY rank_score"  # BM25: 낮을수록 관련도 높음

    else:
        # FTS5 없이 필터만
        sql = """
            SELECT e.*, 0 AS rank_score, '' AS title_snippet, '' AS body_snippet
            FROM emails e
            WHERE 1=1
        """

        if parsed.where_clauses:
            for clause in parsed.where_clauses:
                sql += _and_clause(clause)
            params.extend(parsed.where_params)

        # 빈 검색 → 시간순
        if parsed.sort_by == "received_at_asc":
            sql += " ORDER BY e.received_at ASC"
        else:
            sql += " ORDER BY e.received_at DESC"

    # 페이지네이션
    offset = (page - 1) * per_page
    sql += f" LIMIT {per_page} OFFSET {offset}"

    return sql, params


def build_count_sql(parsed: ParsedQuery) -> Tuple[str, list]:
    """검색 결과 총 건수 쿼리 생성"""
    params = []

    if parsed.fts_query:
        sql = """
            SELECT COUNT(*) as cnt
            FROM emails_fts
            JOIN emails e ON e.id = emails_fts.rowid
            WHERE emails_fts MATCH ?
        """
        params.append(parsed.fts_query)
        if parsed.where_clauses:
            for clause in parsed.where_clauses:
                sql += _and_clause(clause)
            params.extend(parsed.where_params)
    else:
        sql = "SELECT COUNT(*) as cnt FROM emails e WHERE 1=1"
        if parsed.where_clauses:
            for clause in parsed.where_clauses:
                sql += _and_clause(clause)
            params.extend(parsed.where_params)

    return sql, params
