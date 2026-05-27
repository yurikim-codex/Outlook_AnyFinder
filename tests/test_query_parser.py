"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[C06] 쿼리 파서 테스트 — 자연어 → FTS5 변환 12+ 케이스
"""

import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.query_parser import parse_query, _tokenize, _escape_fts


class TestTokenizer:

    def test_01_simple_words(self):
        tokens = _tokenize("프로젝트 보고서")
        assert tokens == ["프로젝트", "보고서"]

    def test_02_quoted_phrase(self):
        tokens = _tokenize('프로젝트 "정확한 구문 검색" 보고서')
        assert len(tokens) == 3
        assert tokens[1] == '"정확한 구문 검색"'

    def test_03_prefix_token(self):
        tokens = _tokenize("from:김철수 견적서")
        assert tokens == ["from:김철수", "견적서"]

    def test_04_mixed(self):
        tokens = _tokenize('from:김철수 "견적서 검토" -반려 첨부:xlsx')
        assert len(tokens) == 4


class TestParseQuery:

    def test_05_empty(self):
        """빈 검색어"""
        p = parse_query("")
        assert p.is_empty is True
        assert p.fts_query == ""

    def test_06_single_keyword(self):
        """단일 키워드"""
        p = parse_query("프로젝트")
        assert "프로젝트" in p.fts_query
        assert p.is_empty is False

    def test_07_multi_keyword(self):
        """복합 키워드 (AND)"""
        p = parse_query("프로젝트 보고서")
        assert "프로젝트" in p.fts_query
        assert "보고서" in p.fts_query
        assert "AND" in p.fts_query

    def test_08_from_prefix(self):
        """from: 접두사"""
        p = parse_query("from:김철수")
        assert "sender_name:김철수" in p.fts_query

    def test_09_to_prefix(self):
        """to: 접두사"""
        p = parse_query("to:이영희 견적서")
        assert "recipients:이영희" in p.fts_query
        assert "견적서" in p.fts_query

    def test_10_subject_prefix(self):
        """subject: 접두사"""
        p = parse_query("subject:견적서")
        assert "subject:견적서" in p.fts_query

    def test_11_attachment_filter(self):
        """attachment: → WHERE절"""
        p = parse_query("attachment:xlsx")
        assert len(p.where_clauses) == 1
        assert "attachment_types" in p.where_clauses[0]
        assert "xlsx" in p.where_params[0]

    def test_12_korean_attachment(self):
        """첨부: 한국어 접두사"""
        p = parse_query("첨부:pdf")
        assert len(p.where_clauses) == 1
        assert "pdf" in p.where_params[0]

    def test_13_folder_filter(self):
        """폴더: → WHERE절"""
        p = parse_query("폴더:받은편지함 견적")
        assert "folder_name" in p.where_clauses[0]
        assert p.where_params[0] == "받은편지함"
        assert "견적" in p.fts_query

    def test_14_date_filter(self):
        """날짜: → WHERE절"""
        p = parse_query("날짜:2026-05")
        assert "received_at" in p.where_clauses[0]
        assert "2026-05" in p.where_params[0]

    def test_15_exclusion(self):
        """제외어 (-반려)"""
        p = parse_query("견적서 -반려")
        assert "NOT" in p.fts_query
        assert "반려" in p.fts_query
        assert "견적서" in p.fts_query

    def test_16_phrase_search(self):
        """구문 검색 ("정확한 구문")"""
        p = parse_query('"정확한 구문 검색"')
        assert '"정확한 구문 검색"' in p.fts_query

    def test_17_complex_combined(self):
        """복합 쿼리: from + 키워드 + 첨부 + 날짜"""
        p = parse_query("from:김철수 견적서 첨부:pdf 날짜:2026-05")
        assert "sender_name:김철수" in p.fts_query
        assert "견적서" in p.fts_query
        assert len(p.where_clauses) == 2  # 첨부 + 날짜

    def test_18_importance_filter(self):
        """중요도 필터"""
        p = parse_query("중요:높음")
        assert "importance" in p.where_clauses[0]
        assert p.where_params[0] == 2

    def test_19_read_filter(self):
        """읽음 상태 필터"""
        p = parse_query("읽음:안읽음")
        assert "is_read" in p.where_clauses[0]
        assert p.where_params[0] == 0

    def test_20_korean_from(self):
        """한국어 접두사 '보낸사람:'"""
        p = parse_query("보낸사람:박지현")
        assert "sender_name:박지현" in p.fts_query

    def test_21_special_chars_escaped(self):
        """특수문자가 이스케이프되어야 한다"""
        result = _escape_fts("hello*world(test)")
        assert "*" not in result
        assert "(" not in result

    def test_22_build_where_sql(self):
        """ParsedQuery.build_where_sql"""
        p = parse_query("폴더:받은편지함 첨부:xlsx")
        where_sql = p.build_where_sql()
        assert "folder_name" in where_sql
        assert "attachment_types" in where_sql
        assert "AND" in where_sql


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
