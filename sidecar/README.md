# OutLook AnyFinder — Python Sidecar IPC 계약서

> **버전**: sidecar 0.9.1 / protocol 1.0
> **소비자**: Tauri Rust Core (`src-tauri/sidecar.rs`) — Phase 2에서 구현
> **근거**: [MIGRATION_PLAN.md](../MIGRATION_PLAN.md) §6 IPC 계약 설계

사이드카는 **모든 비즈니스 로직**(Outlook COM, SQLite/FTS5, 인덱싱, 동기화)을 담당하는
Python 프로세스입니다. `core/` `data/` `utils/` 는 무수정 재사용됩니다.
UI·창·다이얼로그는 일절 가지지 않으며, stdin/stdout **JSON Lines**로만 대화합니다.

---

## 1. 실행 방법

### 개발 (Python)

```powershell
# Mock 모드 (Windows 외 플랫폼은 자동 Mock)
py -3 -m sidecar --mock

# 실 Outlook 모드 (Windows)
py -3 -m sidecar

# 격리된 데이터 디렉터리 사용 (테스트)
py -3 -m sidecar --mock --data-dir C:\temp\anyfinder-test
```

| 인수 | 설명 |
|---|---|
| `--mock` | Mock Outlook 커넥터 사용 (비Windows에서는 자동 적용) |
| `--data-dir PATH` | 데이터 디렉터리 (기본 `%USERPROFILE%\.outlook_anyfinder`) — DB·config.json·로그 위치 |
| `--db-path PATH` | DB 파일만 별도 지정 (기본 `{data-dir}\anyfinder.db`) |
| `--no-stdout-protect` | stdout fd 보호 해제 (디버그용. 프로토콜은 sys.stdout에 남음) |
| `--log-level DEBUG` | 로그 레벨 |
| `--version` / `--help` | 버전/도움말 (**stderr**로 출력 — 프로토콜 보호) |

환경변수: `ANYFINDER_MOCK=1` (mock 강제), `ANYFINDER_DATA_DIR` (데이터 디렉터리)

### 진단 도구 (Rust 없이 테스트)

```powershell
py -3 sidecar\dev_client.py --doctor          # 자동 진단 34항목
py -3 sidecar\dev_client.py --repl            # 대화형 REPL
py -3 sidecar\dev_client.py system.hello      # 단발 명령

# 파라미터 전달 4가지 형식 (PowerShell 따옴표 문제 대응)
py -3 sidecar\dev_client.py search.record keyword=계약서            # 1. key=value
py -3 sidecar\dev_client.py search.query '{"query":"보고서","per_page":5}'  # 2. 작은따옴표 JSON
py -3 sidecar\dev_client.py 'search.query {"query":"보고서"}'          # 3. 한 토큰
'{"patch":{"ui":{"theme":"warm-dark"}}}' | py -3 sidecar\dev_client.py --stdin-json settings.set  # 4. stdin
```

### 프로덕션 빌드 (PyInstaller)

```powershell
powershell -ExecutionPolicy Bypass -File sidecar\build_sidecar.ps1
# → dist\OutlookAnyFinderSidecar\ (onedir) → src-tauri\resources\sidecar\ 로 복사
```

- `--onedir` + `--console` 필수 (콜드 스타트/백신 안정, windowed 모드의 None-stdio 방지)
- 창 숨김은 Rust spawn 시 `CREATE_NO_WINDOW (0x08000000)` 플래그로 처리

---

## 2. 스레딩 모델 (계획 §5 리스크 1 대응)

```
사이드카 프로세스
├── Main Thread       : stdin 읽기(별도 reader 스레드 큐) + dispatch + 빠른 DB 명령
│                       (search/bookmark/settings — SQLite 공유 연결 + RLock)
├── ComWorker Thread  : ★ Outlook COM 접근은 오직 여기서만 (STA, CoInitialize 1회)
│                       장기 작업(sync.plan/execute/run, index.build)도 이 스레드에서 직렬 실행
└── 로그              : 파일(logs\sidecar.log, 회전 2MB×3) + stderr — stdout 절대 사용 금지
```

- 동기화 중에도 `search.query`는 메인 스레드에서 **즉시 응답** (COM 불필요)
- 장기 작업은 최대 1개 동시 실행 (`JOB_ALREADY_RUNNING`으로 중복 차단)
- 작업 실행 중 `sync.cancel`은 메인 스레드에서 즉시 처리 (stop flag 설정)

## 3. stdout 보호 & UTF-8 (계획 §5 리스크 2 + Phase 1 Windows 버그 #1 대응)

- **fd 레벨 분리**: fd 1을 dup하여 프로토콜 전용 채널로 고정 → fd 1은 devnull로 교체.
  Python `print`, 네이티브/C 확장 출력 모두 프로토콜을 오염시킬 수 없음
- `sys.stdout` → `sys.stderr` 리다이렉트 (print는 로그로 감)
- **UTF-8 강제**: `stdio_guard.force_utf8_io()`가 import 전에 stdin/stdout/stderr를
  UTF-8으로 reconfigure. 한국어 Windows(cp949)에서 환경변수 없이도 동작
- **방어 파서**: JSON이 아닌 줄은 `PARSE_ERROR` 응답(id=null) 후 계속 진행 — 크래시 없음
- 검증: `system.debug.print` 명령 + dev_client doctor #32

---

## 4. 메시지 포맷

**Request** (한 줄 = JSON 객체 1개)
```json
{ "id": 42, "cmd": "search.query", "params": { "query": "계약서", "page": 1, "per_page": 20 } }
```

**Response (성공)**
```json
{ "id": 42, "ok": true, "result": { "items": [], "total_count": 0 } }
```

**Response (오류)**
```json
{ "id": 42, "ok": false, "error": { "code": "JOB_NOT_RUNNING", "message": "...", "retryable": false, "details": {} } }
```

**Event** (비동기 push — id 없음)
```json
{ "event": "sync.progress", "data": { "done": 120, "total": 840, "message": "동기화 중..." } }
```

규칙:
- `id`는 요청마다 고유해야 하며 응답은 같은 `id`로 매칭된다 (순서 보장 없음)
- 장기 작업(`sync.*`, `index.*`)은 **완료 시점에** 응답이 온다. 그동안 이벤트가 스트리밍된다
- 파싱 실패 줄에 대한 응답은 `id: null` 로 온다

---

## 5. Command 목록 (42개)

### system (5)

| cmd | params | result |
|---|---|---|
| `system.hello` | — | `{sidecar_version, protocol_version, python_version, platform, pid, use_mock, db_path, db_ok, db_error, outlook_ok, outlook_note, commands_count, started_at, utf8_io, stdout_protected}` — **DB가 깨져 있어도 성공** |
| `system.ping` | — | `{pong, ts}` |
| `system.shutdown` | — | `{ok, message}` — 응답 전송 후 프로세스 정상 종료 (exit 0) |
| `system.commands` | — | `{commands: [...], count}` |
| `system.debug.print` | `{text?}` | `{ok, printed, stdout_protected}` — stdout 오염 방어 검증용 |

### db (7)

| cmd | params | result |
|---|---|---|
| `db.stats` | — | `{email_count, mock_count, bookmark_count, history_count, db_size_mb, db_path, last_sync_time, indexed_range_months, total_indexed, indexing_state, schema_version}` |
| `db.reset` | — | `{removed}` — Mock 데이터 제거 (실 Outlook 동기화 준비) |
| `db.backup` | `{suffix?}` | `{path, size_mb}` — sqlite3 backup API (WAL 안전) |
| `db.integrity` | — | `{ok, message}` — PRAGMA integrity_check |
| `db.schema_version` | `{version?}` | `{schema_version, sidecar_schema_version}` — version 지정 시 기록 |
| `db.clear_history` | — | `{cleared_history, cleared_sessions}` — 검색 기록만 초기화 (북마크 유지) |
| `db.reset_all` | `{confirm: true ★}` | `{ok, email_count}` — **전체 데이터 초기화**(인덱스/북마크/히스토리/메타 + FTS 재구축 + first_run_completed=false). confirm 없으면 INVALID_PARAMS |

### search (5) — ★ COM 불필요, 동기화 중에도 즉시 응답

| cmd | params | result |
|---|---|---|
| `search.query` | `{query?, page=1, per_page=20(≤500), sort_by="rank", contains_search=false, folders?=[], attachment?("has"/"none"/"xlsx"), date_from?, date_to?, record_history=false}` | `{items:[{email, rank_score, title_snippet, body_snippet}], total_count, total_db_count, page, per_page, total_pages, has_next, has_prev, elapsed_ms, query, sort_by}` |
| `search.folders` | — | `{counts: {폴더명: 건수}, total}` |
| `search.record` | `{keyword}` | `{ok, keyword}` — 검색 기록 |
| `search.history` | `{limit=20}` | `{items: [{id, keyword, search_count, last_searched_at}]}` |
| `search.related` | `{keyword, limit?}` | `{keywords: [...]}` |

검색 규칙 (legacy와 동일):
- 기본 포함 검색, `contains_search=false` + 정확한 단어는 FTS5, `+` AND 멀티, 메일주소 LIKE
- `folders` 다중 선택은 **OR 결합** (받은편지함+보낸편지함 = 양쪽 모두) — 별칭(Inbox/Sent Items 등) 자동 흡수
- `sort_by`: `rank` \| `received_at_desc`(=newest) \| `received_at_asc`(=oldest)

### autocomplete (2)

| cmd | params | result |
|---|---|---|
| `autocomplete.suggest` | `{prefix?, limit?}` | `{suggestions: [{keyword, search_count, last_searched_at}]}` — prefix 없으면 최근 기록 |
| `autocomplete.emails` | — | `{emails: [...], count}` — DB에서 추출한 메일주소 후보 (인라인 자동완성용) |

### sync (6) — Outlook COM, 장기 작업

| cmd | params | result |
|---|---|---|
| `sync.meta` | — | `{last_sync_time, indexed_range_months, total_indexed, indexing_state}` |
| `sync.plan` | `{folder_ids?=[6,5], include_subfolders?, incremental=false, range_months?(3/6/12/0), after_date?, mail_after_date?}` | **async** `{plan_id, total_outlook, total_db, new_count, updated_count, deleted_count, *_ids_preview(≤100), skipped_count, has_changes, changes_summary, sync_started_at, scan_after_date, stopped}` + `sync.plan.progress` 이벤트 |
| `sync.execute` | `{plan_id ★필수, folder_ids?, include_subfolders?, incremental?, range_months?}` | **async** `{added, updated, deleted, skipped, errors, elapsed_sec, message, stopped}` + `sync.progress` 이벤트. 완료 시 `last_sync_time`·`indexed_range_months`(병합) 기록 |
| `sync.run` | sync.plan과 동일 (+ `incremental` 기본 true) | **async** 승인 없는 1회성 plan+execute (자동 동기화용). 반환은 sync.execute와 동일 |
| `sync.cancel` | — | `{ok, cancelled: {job_id, kind, ...}}` — 실행 중 작업 없으면 `JOB_NOT_RUNNING` |
| `sync.status` | — | `{running, job}` |

동기화 규칙 (legacy와 동일):
- 증분(`incremental=true`): `LastModificationTime > after_date` + 10분 overlap, **삭제 미감지**
- 전체/기간 스캔: 삭제 감지 포함. `range_months`가 기존 커버리지보다 넓으면 기간 재스캔
- `plan_id`는 서버 메모리에 최근 5개까지 캐시 — 만료 시 `PLAN_NOT_FOUND` (재-plan 필요)

### index (2) — Outlook COM, 장기 작업

| cmd | params | result |
|---|---|---|
| `index.build` | `{folder_ids?=[6,5], include_subfolders=true, range_months?, after_date?}` | **async** `{added, skipped, errors, elapsed_sec, stopped, message}` + `index.progress` 이벤트. 완료 시 `indexed_range_months` 기록 |
| `index.rebuild_fts` | — | **async** `{ok, elapsed_sec}` — FTS5 재구축 |

### bookmark (5)

| cmd | params | result |
|---|---|---|
| `bookmark.list` | — | `{items: [{id, name, query, filters(객체), position, created_at}], count}` |
| `bookmark.add` | `{query ★, name?, filters?}` | `{id, name, query}` |
| `bookmark.remove` | `{id ★}` | `{removed, id}` — **없는 ID는 removed=false** |
| `bookmark.toggle` | `{query ★, filters?}` | `{bookmarked, query}` |
| `bookmark.rename` | `{id ★, name ★}` | `{ok, id, name}` |

### settings (2)

| cmd | params | result |
|---|---|---|
| `settings.get` | — | `{settings, path}` — config.json (기본값 깊은 머지) |
| `settings.set` | `{patch ★}` | `{settings, path}` — patch를 깊은 머지 후 저장. 예 `{"patch":{"ui":{"theme":"light"}}}` |

### preview / mail / outlook / font (7)

| cmd | params | result |
|---|---|---|
| `preview.html` | `{html ★}` | `{text, char_count}` — HTML → 평문 (utils/html_cleaner) |
| `preview.mail` | `{entry_id ★}` | `{email: {..., attachments: [이름...], attachment_type_list}}` |
| `mail.open` | `{entry_id ★}` | **COM** `{ok, entry_id, mock}` — Outlook에서 메일 열기 |
| `mail.export` | `{entry_id ★, dest_path ★}` | **COM** `{path, size}` — .msg 저장 (**실 Outlook 전용**, mock은 NOT_SUPPORTED) |
| `outlook.check` | — | **COM** `{mock, ok, connected, pywin32_imported, version, inbox_name?, inbox_count?, message}` |
| `outlook.folders` | — | **COM** `{folders: [{id, name, display_name, count}]}` |
| `outlook.default_folders` | — | `{folders: [{id, name}], selectable: [6,5,16,3]}` (COM 불필요) |
| `font.list` | — | `{families, count, source: "registry"\|"fallback"}` |

---

## 6. Event 목록

| event | data | 발생 시점 |
|---|---|---|
| `ready` | `{sidecar_version, protocol_version, pid, use_mock, db_ok, commands_count, utf8_io}` | 기동 초기화 완료 — **React는 이 이벤트 후 입력 활성화** |
| `sync.plan.progress` | `{stage:"status"\|"scan", message, done?, total?, folder?}` | sync.plan/sync.run 스캔 중 |
| `sync.progress` | `{done, total, message}` | sync.execute/sync.run 반영 중 |
| `index.progress` | `{done, total, message, folder}` | index.build 중 |
| `error` | `{code, message}` | 장기 작업 실패 시 (응답 error와 별개 push) |

## 7. 오류 코드

| code | retryable | 의미 |
|---|---|---|
| `PARSE_ERROR` | ✗ | JSON Lines 파싱 실패 (해당 줄 무시, 서버 생존) |
| `INVALID_PARAMS` | ✗ | 필수 파라미터 누락/타입 오류 |
| `UNKNOWN_COMMAND` | ✗ | 등록되지 않은 cmd |
| `DB_NOT_AVAILABLE` | ✓ | DB를 열 수 없음 (hello는 계속 동작) |
| `DB_ERROR` | ✓ | DB 작업 중 오류 |
| `OUTLOOK_CONNECT_FAILED` | ✓ | Outlook COM 연결 실패 (미설치/새 Outlook/프로필 문제) |
| `OUTLOOK_NOT_RUNNING` | ✓ | Outlook 미실행 |
| `JOB_ALREADY_RUNNING` | ✓ | 다른 동기화/인덱싱 작업 실행 중 |
| `JOB_NOT_RUNNING` | ✗ | 취소할 작업 없음 |
| `PLAN_NOT_FOUND` | ✗ | plan_id 만료/없음 — sync.plan 재실행 필요 |
| `NOT_SUPPORTED` | ✗ | 현재 모드에서 미지원 (예: mock에서 mail.export) |
| `INTERNAL` | ✗ | 그 외 내부 오류 |

## 8. Rust(Tauri) 측 구현 요구사항 (Phase 2 체크리스트)

1. spawn: `resources/sidecar/OutlookAnyFinderSidecar.exe` 절대경로 + `CREATE_NO_WINDOW`
   + `CREATE_NEW_PROCESS_GROUP`(정상 종료 시 `CTRL_BREAK_EVENT` 전달용)
   + 환경변수 `PYTHONUTF8=1` 전달(이중 안전장치 — 사이드카 자체 강제에 의존하지 말 것)
2. **방어 파서**: stdout 줄 중 JSON 파싱 실패는 로그로 흘려보내고 계속 진행
3. 요청-응답 `id` 매칭 + 이벤트는 `app.emit()`으로 브리지
4. health-check: 주기적 `system.ping` (timeout 5s) — 실패 시 자동 재시작
5. 앱 종료: `system.shutdown` 요청 → 3s 대기 → 폴백 `CTRL_BREAK_EVENT` → 최후 kill
6. **SQLite 직접 쓰기 금지** (계획 §5 리스크 4 — DB 소유권은 사이드카 단독)

## 9. 테스트

```powershell
py -3 -m pytest tests/test_sidecar_ipc.py -q   # 프로토콜 단위 + 통합(프로세스 spawn) 회귀 테스트
py -3 -m pytest tests/ -q                       # 전체 (legacy 198 + sidecar)
py -3 sidecar\dev_client.py --doctor            # 34항목 진단
```

회귀 테스트는 `PYTHONIOENCODING`/`PYTHONUTF8`를 **일부러 제거한 뒤** 실행되어
사이드카가 스스로 UTF-8을 강제하는지 검증한다 (cp949 환경 테스트 포함).
