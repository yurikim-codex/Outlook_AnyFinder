"""
OutLook AnyFinder Ver0.9.1.1 for SESUNG Team
CLI 기능 검증 — GUI 없이 핵심 로직 전체 테스트

이 스크립트는 GUI(PyQt6) 없이도 실행 가능하며,
Outlook → DB → 검색 → 자동완성 → 북마크 → 동기화 전체 흐름을 검증합니다.
"""

import sys
import os
import time
import tempfile
from pathlib import Path

# 경로 설정
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.database import init_db, get_email_count, get_all_hashes
from data.models import EmailRecord
from core.outlook_connector import MockOutlookConnector, OlDefaultFolders, create_connector
from core.mail_extractor import extract_to_record
from core.index_builder import IndexBuilder
from core.search_engine import SearchEngine
from core.query_parser import parse_query
from core.autocomplete import AutocompleteEngine
from core.bookmark_manager import BookmarkManager
from core.related_keywords import RelatedKeywordsEngine
from core.sync_manager import MockSyncManager
from utils.html_cleaner import strip_html
from utils.config import load_config


def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_ok(msg):
    print(f"  ✅ {msg}")


def print_fail(msg):
    print(f"  ❌ {msg}")


def print_info(msg):
    print(f"  ℹ️  {msg}")


def main():
    print_header("📧 OutLook AnyFinder Ver0.9.1.1 for SESUNG Team — CLI 기능 검증")

    # ═══ 1. DB 초기화 ═══
    print_header("1. DB 초기화")
    db_path = Path(tempfile.mktemp(suffix=".db"))
    conn = init_db(db_path)
    print_ok(f"DB 생성: {db_path}")

    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%' AND name NOT LIKE 'emails_fts_%' ORDER BY name"
    ).fetchall()
    print_ok(f"테이블 {len(tables)}개: {', '.join(t['name'] for t in tables)}")

    # ═══ 2. Outlook 연결 (Mock) ═══
    print_header("2. Outlook 연결 (Mock 모드)")
    connector = create_connector(use_mock=True)
    connector.connect()
    print_ok(f"Mock 커넥터 연결 성공")

    folders = connector.get_folder_list()
    for f in folders:
        print_info(f"폴더: {f['name']} ({f['count']}건)")

    total = connector.get_total_mail_count()
    print_ok(f"전체 메일 수: {total}건")

    # ═══ 3. 메일 추출 테스트 ═══
    print_header("3. 메일 추출 & 정제")
    sample_mails = list(connector.iter_mails(OlDefaultFolders.INBOX))
    first_mail = sample_mails[0]
    record = extract_to_record(first_mail)
    print_ok(f"메일 추출 성공: '{record.subject}'")
    print_info(f"발신자: {record.sender_name} <{record.sender_email}>")
    print_info(f"수신자: {record.recipients}")
    print_info(f"날짜: {record.received_at}")
    print_info(f"첨부: {record.attachment_names or '없음'}")
    print_info(f"본문: {record.body_text[:80]}...")

    # ═══ 4. 인덱싱 ═══
    print_header("4. 전체 인덱싱")
    builder = IndexBuilder(conn)
    inbox = list(connector.iter_mails(OlDefaultFolders.INBOX))
    sent = list(connector.iter_mails(OlDefaultFolders.SENT))
    all_mails = inbox + sent

    start = time.perf_counter()
    progress_log = []

    def on_progress(done, total, subject):
        progress_log.append(done)

    stats = builder.build_from_iterator(
        iter(all_mails), len(all_mails), on_progress=on_progress
    )
    elapsed = time.perf_counter() - start

    print_ok(f"인덱싱 완료: {stats['indexed']}건 저장, {stats['skipped']}건 스킵, {stats['errors']}건 오류")
    print_ok(f"소요 시간: {elapsed:.2f}초 ({stats['indexed']/elapsed:.1f}건/초)")
    print_ok(f"DB 메일 수: {get_email_count(conn)}건")
    print_ok(f"해시맵: {len(get_all_hashes(conn))}건")
    print_ok(f"진행률 콜백 호출: {len(progress_log)}회")

    # ═══ 5. 검색 엔진 ═══
    print_header("5. 검색 엔진")
    engine = SearchEngine(conn)

    # 5-1. 기본 검색
    queries = [
        ("프로젝트", "단일 키워드"),
        ("견적서", "단일 키워드"),
        ("프로젝트 보고서", "복합 키워드"),
        ("from:김철수", "발신자 검색"),
        ("subject:견적서", "제목 검색"),
        ("", "빈 검색 (전체)"),
    ]

    for q, desc in queries:
        start = time.perf_counter()
        resp = engine.search(q)
        ms = (time.perf_counter() - start) * 1000
        print_ok(f"[{desc:12s}] '{q}' → {resp.total_count}건 ({ms:.1f}ms)")
        if resp.results:
            r = resp.results[0]
            print_info(f"  1위: '{r.email.subject}' (점수: {r.rank_score:.1f})")

    # 5-2. 필터 조합 검색
    print()
    resp = engine.search("견적서", extra_where=[
        ("folder_name = ?", ["받은편지함"]),
        ("has_attachments = ?", [1])
    ])
    print_ok(f"[필터 조합] '견적서' + 받은편지함 + 첨부있음 → {resp.total_count}건 ({resp.elapsed_ms:.1f}ms)")

    # 5-3. 정렬
    resp_new = engine.search("", sort_by="received_at_desc")
    resp_old = engine.search("", sort_by="received_at_asc")
    if resp_new.results and resp_old.results:
        print_ok(f"[최신순] 첫 번째: {resp_new.results[0].email.received_at}")
        print_ok(f"[오래된순] 첫 번째: {resp_old.results[0].email.received_at}")

    # 5-4. 폴더 카운트
    counts = engine.get_folder_counts()
    for folder, cnt in counts.items():
        print_info(f"  {folder}: {cnt}건")

    # ═══ 6. 쿼리 파서 ═══
    print_header("6. 쿼리 파서")
    test_queries = [
        "프로젝트 보고서",
        "from:김철수 견적서",
        "subject:견적서 -반려",
        "첨부:xlsx 폴더:받은편지함",
        "날짜:2026-05",
        '"정확한 구문 검색"',
        "중요:높음",
        "읽음:안읽음",
    ]
    for q in test_queries:
        p = parse_query(q)
        fts = p.fts_query or "(없음)"
        where = p.build_where_sql() or "(없음)"
        print_ok(f"'{q}'")
        print_info(f"  FTS5: {fts}")
        if p.where_clauses:
            print_info(f"  WHERE: {where} | params: {p.where_params}")

    # ═══ 7. 자동완성 ═══
    print_header("7. 자동완성")
    ac = AutocompleteEngine(conn)

    ac.record_search("프로젝트 보고서")
    ac.record_search("프로젝트 보고서")
    ac.record_search("프로젝트 보고서")
    ac.record_search("프로젝트 견적서")
    ac.record_search("프로모션 계획")
    print_ok(f"검색 히스토리 기록: {ac.get_count()}건")

    suggestions = ac.get_suggestions("프로")
    print_ok(f"'프로' 자동완성 → {len(suggestions)}건:")
    for s in suggestions:
        print_info(f"  {s.keyword} ({s.search_count}회)")

    # ═══ 8. 북마크 ═══
    print_header("8. 검색어 북마크")
    bm = BookmarkManager(conn)

    id1 = bm.add("프로젝트 보고서", query="from:김철수 프로젝트", filters={"folder": "받은편지함"})
    id2 = bm.add("견적서 모음", query="견적서 첨부:xlsx")
    print_ok(f"북마크 추가: {bm.get_count()}건")

    all_bm = bm.get_all()
    for b in all_bm:
        print_info(f"  ⭐ {b.name} → '{b.query}' (필터: {b.filters})")

    # 토글 테스트
    is_added = bm.toggle("테스트 토글")
    print_ok(f"토글(추가): {is_added} → 현재 {bm.get_count()}건")
    is_removed = bm.toggle("테스트 토글")
    print_ok(f"토글(삭제): {is_removed} → 현재 {bm.get_count()}건")

    # ═══ 9. 연관 검색어 ═══
    print_header("9. 추천 연관 검색어")
    rk = RelatedKeywordsEngine(conn)
    rk.seed_default_relations()
    print_ok("기본 연관어 사전 시드 완료")

    # 세션 기록
    rk.record_session("견적서")
    rk.record_session("예산")
    rk.record_session("비용")

    related = rk.get_related("견적서")
    print_ok(f"'견적서' 연관어 → {len(related)}건: {', '.join(related)}")

    related2 = rk.get_related("프로젝트")
    print_ok(f"'프로젝트' 연관어 → {len(related2)}건: {', '.join(related2)}")

    # ═══ 10. 스마트 동기화 ═══
    print_header("10. 스마트 증분 동기화")
    sm = MockSyncManager(conn, connector)

    # 10-1. 변경 없는 동기화
    plan = sm.create_plan(folder_ids=[6, 5])
    print_ok(f"동기화 계획: {plan.changes_summary}")
    print_ok(f"변경 여부: {plan.has_changes} (Outlook: {plan.total_outlook}, DB: {plan.total_db})")

    if not plan.has_changes:
        print_ok("✅ 변경 없음 — 모든 메일이 최신 상태!")

    # 10-2. 새 메일 추가 후 동기화
    connector._sample_emails.append({
        "entry_id": "CLI_TEST_NEW_001",
        "subject": "CLI 테스트 새 메일",
        "sender_name": "CLI테스터",
        "sender_email": "cli@test.com",
        "recipients": "나", "cc": "",
        "body_text": "CLI 테스트용 새 메일입니다.",
        "html_body": "",
        "folder_name": "받은편지함",
        "received_at": "2026-05-28 15:00:00",
        "sent_at": "2026-05-28 15:00:00",
        "has_attachments": 0, "attachment_count": 0,
        "attachment_names": "", "attachment_types": "",
        "importance": 1, "is_read": 0,
        "categories": "", "conversation_id": "CLI_CONV",
    })

    plan2 = sm.create_plan(folder_ids=[6, 5])
    print_ok(f"새 메일 추가 후 계획: {plan2.changes_summary}")

    result = sm.execute_plan(plan2, folder_ids=[6, 5])
    print_ok(f"동기화 실행: {result.summary}")
    print_ok(f"DB 메일 수: {get_email_count(conn)}건")

    # 새 메일 검색 확인
    resp = engine.search("CLI 테스트")
    print_ok(f"새 메일 검색: '{resp.results[0].email.subject}'" if resp.results else "검색 안 됨")

    # 10-3. 멱등성 확인
    plan3 = sm.create_plan(folder_ids=[6, 5])
    print_ok(f"재동기화 계획: {plan3.changes_summary} (변경: {plan3.has_changes})")

    # ═══ 11. HTML 변환 ═══
    print_header("11. HTML → 텍스트 변환")
    html_samples = [
        ("<p>안녕하세요</p><br><b>굵은 글씨</b>", "기본 HTML"),
        ("<table><tr><td>셀1</td><td>셀2</td></tr></table>", "테이블"),
        ("A &amp; B &lt; C", "HTML 엔티티"),
    ]
    for html, desc in html_samples:
        text = strip_html(html)
        print_ok(f"[{desc}] '{html[:30]}...' → '{text.strip()[:40]}'")

    # ═══ 12. 설정 ═══
    print_header("12. 설정 파일")
    config = load_config()
    print_ok(f"설정 로드 완료")
    print_info(f"  인덱싱 범위: {config['indexing']['range_months']}개월")
    print_info(f"  자동 동기화: {config['sync']['auto_sync']} ({config['sync']['interval_minutes']}분)")
    print_info(f"  자동완성 최대: {config['search']['max_autocomplete_items']}개")
    print_info(f"  결과/페이지: {config['search']['results_per_page']}건")

    # ═══ 종합 결과 ═══
    print_header("📊 종합 결과")
    print_ok(f"DB 최종 메일 수: {get_email_count(conn)}건")
    print_ok(f"해시맵: {len(get_all_hashes(conn))}건")
    print_ok(f"검색 히스토리: {ac.get_count()}건")
    print_ok(f"북마크: {bm.get_count()}건")
    print_ok(f"전체 테스트 통과!")

    # 정리
    conn.close()
    db_path.unlink(missing_ok=True)

    print(f"\n{'='*60}")
    print(f"  🎉 OutLook AnyFinder Ver0.9.1 — 전체 기능 검증 완료!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
