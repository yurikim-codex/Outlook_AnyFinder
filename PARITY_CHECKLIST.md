# Parity 체크리스트 — PyQt6(Ver0.9) ↔ React+Tauri(Ver1.0)

> Phase 4-1 산출물. legacy `legacy_pyqt/ui/*`의 **모든 사용자-facing 기능**을 1:1 대조했다.
> 검증 열: `auto` = tests/test_sidecar_ipc.py 또는 `frontend/smoke.mjs`로 자동 검증됨,
> `S##` = docs/MANUAL_TEST_SCENARIOS.md 시나리오 번호, `Win` = Windows 실기기 필수.
> 기준 커밋: Phase 4 반영 후 HEAD.

## 범례
- ✅ parity 확보  |  ➕ 신규 기능(legacy에 없었음)  |  ⚠️ 의도적 변경(사용자 인지 필요)  |  🖥️ Windows에서만 검증 가능

## 1. 검색

| # | legacy 기능 (모듈) | 새 구현 | 검증 | 상태 |
|---|---|---|---|---|
| 1 | 키워드 검색 — 제목/본문/보낸사람 (search_bar) | `search.query` + ResultList | auto(test_20~31), S1 | ✅ |
| 2 | 포함 검색 / "정확한 단어만" (search_bar) | `contains_search` 파라미터 + Header 체크박스 | S2 | ✅ |
| 3 | 다중 단어 AND `바이오+견적서` (search_bar) | core 쿼리 파서 무수정 재사용 | S3 | ✅ |
| 4 | 메일 주소 검색 (search_bar) | `search.query` + `autocomplete.emails` | S4 | ✅ |
| 5 | 자동완성 팝업 (autocomplete_popup) | Header 드롭다운(`autocomplete.suggest`, 200ms 디바운스) | S5 | ✅ ⚠️ 지연값 설정(300ms) 대신 200ms 고정 |
| 6 | 검색 기록 저장 (search_bar) | `record_history` + `search.history` | auto(test_24), S5 | ✅ |
| 7 | 연관 검색어 (result_list 하단) | `search.related` + `RelatedChips` (결과 상단 칩 — 클릭 시 재검색. 검색기록 접두사/세션/정적사전 기반) | auto(사이드카 related 테스트), S5 | ✅ |

## 2. 필터

| # | legacy 기능 (filter_bar) | 새 구현 | 검증 | 상태 |
|---|---|---|---|---|
| 8 | 폴더 다중 선택 | FilterChips + Sidebar (OR 결합 — legacy AND 잠재버그 수정) | auto(test_26), S6 | ✅ |
| 9 | 첨부파일 있음만 | `has_attachment` 칩 | S7 | ✅ |
| 10 | 기간 필터 | `range_months` 셀렉트 | S8 | ✅ |
| 11 | 정렬 (관련도/최신/오래된) | `sort_by` + 설정 `search.default_sort` | S9 | ✅ |

## 3. 결과·미리보기

| # | legacy 기능 (result_list/mail_preview) | 새 구현 | 검증 | 상태 |
|---|---|---|---|---|
| 12 | 페이지네이션 | ResultList 하단 (per_page=settings) | auto(test_22), S11 | ✅ |
| 13 | 카드: 스니펫/첨부/중요/안읽음 | MailCard | S11 | ✅ |
| 14 | 10,000건 스크롤 | @tanstack/react-virtual 가상 스크롤 | S11 | ✅ ➕ 성능 |
| 15 | 본문 미리보기 (HTML 렌더) | `preview.mail` 평문 렌더 | S12 | ✅ ⚠️ HTML→평문+sanitize( XSS 제거, 서식 표현 sacrificed) |
| 16 | Outlook에서 열기 | `mail.open` | S12 | 🖥️ |
| 17 | 메일 내보내기 | `mail.export` | S12 | 🖥️ |

## 4. 사이드바·북마크

| # | legacy 기능 (sidebar) | 새 구현 | 검증 | 상태 |
|---|---|---|---|---|
| 18 | 폴더별 건수 | `search.folders` | smoke, S6 | ✅ |
| 19 | 북마크 추가/삭제/클릭 검색 | `bookmark.*` + Sidebar/헤더 별표 | auto(test_32~36), S10 | ✅ |
| 20 | 인덱스/DB 통계 표시 | `db.stats` | smoke | ✅ |

## 5. 동기화·인덱싱

| # | legacy 기능 (sync_folder_dialog/indexing_dialog/main_window) | 새 구현 | 검증 | 상태 |
|---|---|---|---|---|
| 21 | 폴더 선택 동기화 (plan→승인→execute) | SyncFolderDialog (`sync.plan/execute`) | auto(test_40~45), S16 | ✅ |
| 22 | 동기화 진행률/취소 | `sync.progress` 이벤트 + 취소 버튼 | S16 | ✅ |
| 23 | 증분 동기화 옵션 | `incremental` 파라미터 | S16 | ✅ |
| 24 | 첫 실 인덱싱 대화상자 | FirstRunDialog + `index.build` + `index.progress` | S13 | ✅ |
| 25 | 자동 동기화 타이머 + busy 지연 | store 스케줄러 (`sync.interval_minutes`, 30초 틱) | S15 | ✅ |
| 26 | 동기화 중 검색 가능 | JobRegistry 분리 (COM 스레드 vs IPC) | auto(test_44), S16 | ✅ |

## 6. 설정·데이터

| # | legacy 기능 (settings_dialog/utils/config) | 새 구현 | 검증 | 상태 |
|---|---|---|---|---|
| 27 | config.json 위치·스키마 | **동일 파일·동일 스키마** (키 이름 변경 금지) | auto(test_19) | ✅ |
| 28 | 자동 동기화 on/off·간격 | 설정>동기화 (`sync.auto_sync/interval_minutes`) | test_19, S14 | ✅ |
| 29 | 기본 동기화 기간/하위폴더 | 설정>동기화 (`indexing.range_months/include_subfolders`) | test_19, S14 | ✅ |
| 30 | 페이지당 건수/기본 정렬 | 설정>검색 (`search.results_per_page/default_sort`) | test_19, S14 | ✅ |
| 31 | 테마 (dark/light) | 3테마 (+warm-dark ➕) | S14 | ✅ |
| 32 | — (legacy 없음) | 데이터 관리: 기록 삭제/전체 초기화/백업/무결성/FTS 재구축 ➕ | auto(test_16/17), S14 | ➕ |

## 7. 앱 셸·비기능

| # | legacy 동작 | 새 동작 | 검증 | 상태 |
|---|---|---|---|---|
| 33 | 창 닫기 = 종료 | **닫기 = 트레이 숨김**, 트레이 "종료"만 종료 | S19 | ⚠️ 정책 변경(검토 요청) |
| 34 | — (legacy 없음) | 트레이 아이콘(열기/지금 동기화/종료) ➕ | S18 | ➕ 🖥️ |
| 35 | — (legacy 없음) | 단일 인스턴스(두 번째 실행 시 창 포커스) ➕ | S19 | ➕ 🖥️ |
| 36 | — (legacy 없음) | 창 크기/위치 기억 ➕ | S19 | ➕ 🖥️ |
| 37 | PyInstaller 기동 3~6초 | Tauri 셸 0.3~0.8초 + 사이드카 백그라운드 | S19 | ✅ ➕ |
| 38 | cp949/stdout 오염/좀비 프로세스 방어 | sidecar 자가 UTF-8 강제·fd 보호·graceful shutdown | auto(test_07~17) | ✅ |
| 39 | 오류 대화상자 | Toast(오류 코드 표시) + 사이드카 자동 재시작 배너 | S17 | ✅ ⚠️ 모달→토스트 |
| 40 | — (legacy 없음) | 버전 불일치 감지 배너 (`system.info`) ➕ | auto(test_18) | ➕ |

## 집계

| 판정 | 건수 |
|---|---|
| ✅ parity (자동 검증 포함) | 31 |
| 🖥️ Windows 실기기 검증 대기 (기능 자체는 구현 완료) | 6 (16,17,34,35,36,37) |
| ⚠️ 의도적 변경 (사용자 인지) | 6 (5,8은 버그 수정 포함, 15,33,39 + 자동완성 지연) |
| ➕ 신규 | 8 |
| 미완 (후속) | 0 |

**체크리스트 100% 통과 정의**: ✅ 행 전부 자동 테스트 그린 + 🖥️ 행 전부 Windows 시나리오(S12,S18,S19) 통과 + ⚠️ 행 사용자 승인.
현재 자동 부분 그린(294 passed). Windows 행은 스파이크 A/B와 함께 사용자 머신에서 확인 예정.
