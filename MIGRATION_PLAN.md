# React + Tauri 전환 타당성 검토 및 실행 계획

**문서 버전**: 1.0
**작성일**: 2026-10-02
**대상**: OutLook AnyFinder Ver0.9.1 (PyQt6 → React + Tauri + Python Sidecar)
**판정**: ✅ **전환 가능 (Feasible)** — 단, 조건부 권장

---

## 0. 결론 요약 (TL;DR)

| 질문 | 답 |
|---|---|
| 구조 변경이 가능한가? | **가능합니다.** 레퍼런스 그림 그대로 구현 가능합니다. |
| 왜 가능한가? | 현재 `core/` `data/` `utils/` 전체에 **PyQt6 의존성이 0건**입니다. 이미 IPC 준비가 끝난 상태입니다. |
| 가장 큰 이득 | UI 자유도(폰트·그래픽 완전 제어), 시작 속도, 대량 리스트 렌더링 성능 |
| 가장 큰 손실 | 개발 복잡도 증가, 빌드 파이프라인 2개(Rust + Python), COM 스레딩 재설계 필요 |
| 예상 기간 | **집중 투입 4~5주 / 파트타임 8~10주** (현재 약 25% 진행) |
| 권장 전략 | **빅뱅 전환 금지.** 같은 저장소에서 병렬 개발 후 기능 동등성(parity) 달성 시 교체 |
| 최대 리스크 | Outlook COM STA 스레딩 모델, 사이드카 stdout 오염, PyInstaller 배포 |

> **핵심 인사이트**: 이 프로젝트는 "전면 재작성"이 아니라 **"UI 계층 교체 + 실행 컨테이너 교체"** 입니다.
> 비즈니스 로직 2,610줄(core) + 457줄(data) + 209줄(utils)은 **단 한 줄도 고치지 않고** 사이드카로 그대로 이식됩니다.

---

## 1. 현재 구조 진단 (실측 데이터)

### 1.1 코드 자산 실측

```
총 Python 11,685줄 / 59개 파일
├── ui/         4,098줄   ← PyQt6. 전환 시 재작성 대상
├── core/       2,610줄   ← ★ PyQt6 의존 0건 → 그대로 재사용
├── tests/      2,528줄   ← ★ core 계약 유지 시 그대로 재사용
├── main.py 등  1,242줄   ← AppController/tray/빌드. 대부분 이전/폐기
├── workers/      541줄   ← QThread. 사이드카 워커로 소량 재작성
├── data/         457줄   ← ★ PyQt6 의존 0건 → 그대로 재사용
└── utils/        209줄   ← ★ PyQt6 의존 0건 → 그대로 재사용
```

### 1.2 결정적 검증 결과

```bash
$ grep -rn "PyQt6\|QObject\|QThread\|pyqtSignal" core/ data/ utils/
core/outlook_connector.py:57:  # ★ COM 스레드 초기화 (QThread에서 호출 시 필수)   ← 주석 1건뿐
```

**`core/`, `data/`, `utils/` 에 실제 Qt import가 단 한 건도 없습니다.**
이것이 이 프로젝트의 전환이 "가능"을 넘어 "쉬운" 이유입니다.
비즈니스 로직이 이미 프레임워크 독립적으로 작성되어 있습니다.

### 1.3 현재 데이터 계층

| 항목 | 값 |
|---|---|
| DB 엔진 | SQLite + FTS5 (전문 검색) |
| DB 위치 | `%USERPROFILE%\.outlook_anyfinder\anyfinder.db` |
| 연결 방식 | `check_same_thread=False`, `timeout=30.0` |
| 설정 위치 | `%USERPROFILE%\.outlook_anyfinder\` |
| 검색 API | `SearchEngine.search(query, page, per_page, sort_by, extra_where, ...)` |
| 동기화 API | `SyncManager.create_plan()` → `execute_plan(plan, should_stop=...)` |

### 1.4 현재 구조의 실제 문제점

| 문제 | 원인 |
|---|---|
| 폰트/그래픽이 마음에 안 듦 | QSS는 CSS의 부분집합. 폰트 대체(fallback), 벡터 그래픽, 애니메이션 표현에 한계 |
| 테마 바꿀 때마다 글자 대비 깨짐 | QSS 전역 재적용 시 위젯별 상태 스타일 충돌. 구조적 한계 |
| 대량 메일 리스트 스크롤 끊김 | QWidget 카드 1건 = 위젯 N개. 1,000건만 넘어도 렌더링 부하 |
| 위젯 잔상 (사이드바 접기 등) | Qt 레이아웃 재계산 타이밍 문제. 반복적 패치 필요 |

이 4가지는 **PyQt6로 계속 패치해도 근본 해결이 어려운 항목**입니다. 전환의 실질적 명분이 여기에 있습니다.

---

## 2. 목표 구조 (레퍼런스 그림 → 실제 매핑)

```
┌──────────────────────────────────────────────────────────────┐
│  ① React Frontend                                            │
│                                                              │
│  App Shell / Sidebar / Header / Pages / Preview Panel        │
│  Context + Reducer / CSS Design Tokens / Components          │
│                                                              │
│  Vite 7 + React 19 + TypeScript + Tailwind 4                 │
│  가상 스크롤(@tanstack/react-virtual) / lucide-react 아이콘     │
│  Pretendard Variable 폰트 (나눔고딕 폴백)                       │
└───────────────────────────┬──────────────────────────────────┘
                            │  invoke("search_mails", {query, page})
                            │  listen("sync://progress", cb)
┌───────────────────────────▼──────────────────────────────────┐
│  ② Tauri Rust Core                                           │
│                                                              │
│  Command API / Validation / Process Lifecycle                │
│  Window / Dialog / File Access / Security / Logging          │
│                                                              │
│  · 사이드카 프로세스 생명주기 관리 (spawn / health / 재시작)      │
│  · JSON Lines 파서 + 요청-응답 매칭(id) + 이벤트 라우팅           │
│  · 입력 검증, 경로 검증, CSP, 단일 인스턴스, 트레이, 자동 시작      │
└───────────────────────────┬──────────────────────────────────┘
                            │  stdin/stdout JSON Lines IPC
                            │  {"id":1,"cmd":"search.query","params":{...}}
                            │  {"id":1,"ok":true,"result":{...}}
                            │  {"event":"sync.progress","data":{...}}
┌───────────────────────────▼──────────────────────────────────┐
│  ③ Python Sidecar Executable                                 │
│                                                              │
│  기존 Python 업무 로직                                         │
│  pywin32 / BeautifulSoup / 파일 처리 / 분석 / 자동화            │
│                                                              │
│  PyInstaller 로 단일 실행 파일 생성                              │
│                                                              │
│  ★ core/ data/ utils/ 2,610+457+209줄 무수정 이식               │
└──────────────────────────────────────────────────────────────┘
```

### 2.1 각 계층의 책임 경계

| 계층 | 책임 | 하지 않는 것 |
|---|---|---|
| React | 렌더링, 상호작용, 로컬 UI 상태, 가상 스크롤 | DB 접근, COM 접근, 파일 시스템 |
| Rust/Tauri | 프로세스 관리, IPC 중계, 이벤트 라우팅, 보안, 로깅 | 비즈니스 로직, 검색 SQL |
| Python Sidecar | **모든 비즈니스 로직**, Outlook COM, SQLite, 인덱싱 | UI, 창, 다이얼로그 |

이 경계를 지키면 3계층을 각각 독립적으로 테스트/교체할 수 있습니다.

---

## 3. 타당성 판정

### 3.1 가능 근거 (3가지)

**① 비즈니스 로직이 이미 프레임워크 독립적**
`core/` `data/` `utils/` 에 Qt 의존 0건. 그대로 import해서 사이드카에 넣으면 동작합니다.

**② 사이드카 패턴의 검증된 레퍼런스가 이미 존재**
같은 개발자가 만든 DocuFinder(`chrisryugj/Docufinder`)가 **Tauri 2 + React 19 + Vite 7 + Tailwind 4 + NSIS + 자동 업데이트 + Python 스크립트 자원 번들** 구조로 이미 상용 배포 중입니다.
`src-tauri/scripts/` 에 다음이 실제로 존재합니다:
- `bundle-kordoc.ps1` — 외부 런타임 + 소스를 `src-tauri/resources/` 에 번들
- `download-vcredist.ps1` — VC++ 재배포판 처리
- `generate-signing-key.ps1` / `create-cert.ps1` — 서명
- `release.sh` — 릴리즈 자동화

즉 **막히면 그대로 참고할 수 있는 실전 코드가 이미 손안에 있습니다.**

**③ 테스트 자산이 살아남음**
`tests/` 2,528줄 / 198개 테스트가 `core` 계약을 검증합니다.
전환 중에도 `pytest` 198 passed가 계속 통과하면 **회귀가 없다는 것이 수치로 증명**됩니다.
이건 전환 프로젝트에서 매우 드문 강력한 안전망입니다.

### 3.2 주의 사항 (5가지)

| # | 주의점 | 설명 |
|---|---|---|
| 1 | **속도 개선은 전부가 아님** | UI 렌더링·시작 속도는 개선되지만, **동기화 속도는 Outlook COM이 병목**이라 변하지 않습니다. |
| 2 | **개발 복잡도 2배** | Rust 툴체인 + Node 툴체인 + Python 툴체인. 빌드 실패 시 원인 추적이 3계층에 걸침 |
| 3 | **배포 크기 감소 아님** | Python 런타임이 여전히 포함되므로 패키지 크기는 비슷하거나 약간 증가 |
| 4 | **초기 2~3개월 기능 정지** | 전환 기간 동안 신규 기능 추가가 어렵습니다. |
| 5 | **사이드카 크래시 = 앱 전체 마비** | Python 프로세스가 죽으면 검색/동기화가 전부 멈춤. 감시·자동 재시작 필수 |

---

## 4. 핵심 판단: 무엇을 남기고 무엇을 버리는가

| 자산 | 규모 | 처리 | 근거 |
|---|---|---|---|
| `core/` | 2,610줄 | ✅ **무수정 이식** | Qt 의존 0. COM/검색/동기화의 핵심 |
| `data/` | 457줄 | ✅ **무수정 이식** | Qt 의존 0. FTS5 스키마 유지 |
| `utils/` | 209줄 | ✅ **무수정 이식** | Qt 의존 0 |
| `tests/` | 2,528줄 | ✅ **거의 무수정 유지** | 회귀 안전망 |
| `workers/` | 541줄 | 🔄 **재작성 (소량)** | QThread → 사이드카 워커 스레드 |
| `ui/` | 4,098줄 | ❌ **폐기 → React 재작성** | 이게 전환의 목적 |
| `main.py` | 718줄 | 🔄 **분해 이전** | AppController → Rust(생명주기) + React(UI) |
| 빌드 스크립트 | ~400줄 | 🔄 **교체** | PyInstaller → PyInstaller(사이드카) + `tauri build` |

**결론: 11,685줄 중 약 5,800줄(50%)이 그대로 살아남습니다.**

---

## 5. 최대 리스크 5개와 대응

### 🔴 리스크 1: Outlook COM 스레딩 (STA) — **최대 위험**

**문제**
현재는 `QThread` 워커가 각자 `pythoncom.CoInitialize()`를 호출합니다.
사이드카는 단일 프로세스이므로, Outlook 개체를 어느 스레드에서 만질지 재설계해야 합니다.
잘못 설계하면 `RPC_E_WRONG_THREAD`, `0x800401F0 (CO_E_NOTINITIALIZED)` 같은 오류가 간헐 발생합니다.
**Outlook COM은 재현 안 되는 간헐 오류가 가장 무서운 상대입니다.**

**대응 (권장 설계)**
```
사이드카 프로세스
├── Main Thread     : IPC 읽기/쓰기 (stdout/stderr 전담)
├── COM Thread (1개, STA 고정) : ★ Outlook 개체 접근은 오직 여기서만
│                      pythoncom.CoInitialize() 1회
│                      Job Queue로 작업 수신 → 결과를 이벤트로 push
└── DB Thread Pool  : SQLite 읽기 전용 병렬 (WAL 모드)
```
- **Outlook 접근을 단일 STA 스레드로 직렬화** → 스레딩 오류 원천 차단
- 검색(FTS5)은 별도 스레드에서 병렬 → 체감 속도 유지
- 검색은 COM이 필요 없으므로 **동기화 중에도 검색이 즉시 응답** (현재 구조보다 개선되는 지점)

**검증 방법**: Phase 1에서 `outlook_com_check.py`를 사이드카 경유로 100회 반복 호출하는 스트레스 테스트.

---

### 🟠 리스크 2: 사이드카 stdout 오염 — **가장 흔한 실패 원인**

**문제**
JSON Lines 프로토콜이 `stdout`을 쓰는데, 현재 `main.py:_setup_logging()`이 콘솔에 로그를 출력합니다.
`print()` 한 줄, 경고 한 줄만 섞여도 프로토콜 파서가 즉사합니다.
pywin32/BeautifulSoup이 경고를 stdout으로 뱉는 경우도 있습니다.

**대응**
```python
# sidecar/__main__.py 최상단 (import 이전!)
import sys, os
_real_stdout = sys.stdout
sys.stdout = sys.stderr          # 이후 모든 print/log는 stderr로
os.dup2(os.open(os.devnull, os.O_WRONLY), 1)  # fd 레벨까지 차단
```
- 프로토콜 전용 채널을 `_real_stdout` 으로 고정 (절대 오염 불가)
- 로그는 **파일**로만: `%USERPROFILE%\.outlook_anyfinder\logs\sidecar.log`
- Rust 쪽에도 **방어 파서**: JSON 파싱 실패한 줄은 로그로 흘려보내고 계속 진행 (크래시 금지)

**검증 방법**: Phase 1에서 의도적으로 `print()` 를 10곳에 심고 정상 동작 확인.

---

### 🟡 리스크 3: PyInstaller 사이드카 배포

**문제**
- `--onefile` 은 실행 시마다 임시 폴더 압축 해제 → 콜드 스타트 3~5초, 백신 오탐 빈발
- Tauri의 `externalBin` 은 단일 파일을 기대 → onedir 배포와 충돌

**대응**
- **`--onedir` 사용** (콜드 스타트 1~2초, 백신 안정)
- `externalBin` 대신 **리소스 디렉터리 방식** 채택 (DocuFinder의 `resources/kordoc/**` 와 동일 패턴)
  ```json
  "bundle": {
    "resources": ["resources/sidecar/**/*"]
  }
  ```
- 실행 시 `resource_dir()/resources/sidecar/OutlookAnyFinderSidecar.exe` 를 절대경로로 spawn
- Windows에서 창 숨김 필수: Rust `Command` 에 `CREATE_NO_WINDOW (0x08000000)` 플래그

**검증 방법**: Phase 5에서 `tauri build` 후 NSIS 설치 → 실제 배포본에서 사이드카 기동 확인.

---

### 🟡 리스크 4: SQLite 이중 쓰기 (DB 소유권)

**문제**
Rust와 Python이 같은 `.db` 파일을 동시에 쓰면 **손상 위험**이 있습니다.
FTS5 인덱스는 특히 깨지면 재색인(수 시간)이 필요합니다.

**대응 — 명확한 소유권 규칙**
```
[쓰기] Python Sidecar 단독 소유  ← 절대 규칙
[읽기] Phase 2까지는 Python 경유 (IPC)
       Phase 3 이후 Rust가 mode=ro + WAL 로 읽기 전용 직접 접근 (선택적 최적화)
```
- Rust가 직접 읽을 경우 반드시 `file:...?mode=ro&immutable=0` + WAL
- **Rust에서 INSERT/UPDATE/DELETE 는 금지**
- 마이그레이션 전 백업: `anyfinder.db.bak-v0.9.1` 자동 생성

**대응(추가)**: 스키마 버전 테이블(`meta.schema_version`)로 사이드카/프론트 버전 불일치 감지.

---

### 🟢 리스크 5: 시작 체감 속도

**문제**
Tauri 셸은 0.3초에 뜨지만 사이드카는 1.5~3초 걸립니다.
사이드카 준비 전에 사용자가 검색하면 "먹통"처럼 보입니다.

**대응**
1. Rust `setup()` 에서 **창 표시와 동시에 사이드카 spawn** (직렬 대기 금지)
2. React는 즉시 셸 렌더링 → 검색창은 `엔진 준비 중...` 상태 표시
3. 사이드카가 `{"event":"ready"}` 를 보내면 입력 활성화
4. **사이드카는 앱 종료 시까지 절대 죽이지 않음** (재시작 비용 회피). 트레이 상주.

---

## 6. IPC 계약 설계

### 6.1 메시지 포맷

**Request (React → Rust → Sidecar)**
```json
{ "id": 42, "cmd": "search.query",
  "params": { "query": "계약서", "page": 1, "per_page": 50, "sort_by": "rank" } }
```

**Response (Sidecar → Rust → React)**
```json
{ "id": 42, "ok": true,
  "result": { "items": [...], "total_count": 1832, "elapsed_ms": 41.2, "page": 1 } }
```

**Error**
```json
{ "id": 42, "ok": false, "error": { "code": "OUTLOOK_NOT_RUNNING", "message": "Outlook이 실행 중이 아닙니다", "retryable": true } }
```

**Event (비동기 push, id 없음)**
```json
{ "event": "sync.progress", "data": { "done": 120, "total": 840, "folder": "받은 편지함", "message": "스캔 중..." } }
```

### 6.2 Command 전체 목록 (기존 Python API 매핑)

| cmd | 기존 Python 소스 | 반환 |
|---|---|---|
| `system.hello` | (신규) 핸드셰이크 | `{version, db_path, outlook_ok}` |
| `system.shutdown` | (신규) 정상 종료 | `{ok}` |
| `db.stats` | `database.get_email_count` | `{email_count, mock_count}` |
| `db.reset` | `database.purge_mock_data` | `{removed}` |
| `search.query` | `SearchEngine.search` | `{items, total_count, elapsed_ms}` |
| `search.folders` | `SearchEngine.get_folder_counts` | `{counts}` |
| `search.related` | `related_keywords` | `{keywords}` |
| `autocomplete.suggest` | `autocomplete` | `{suggestions}` |
| `sync.plan` | `SyncManager.create_plan` | `{plan}` |
| `sync.execute` | `SyncManager.execute_plan` | `{stats}` |
| `sync.cancel` | `should_stop` 콜백 | `{ok}` |
| `bookmark.list` | `bookmark_manager` | `{items}` |
| `bookmark.add` / `.remove` | `bookmark_manager` | `{ok}` |
| `preview.html` | `html_cleaner` | `{html, text}` |
| `mail.open` | `outlook_connector` | `{ok}` (Outlook에서 열기) |
| `mail.export` | (신규/기존) | `{path}` |
| `settings.get` / `.set` | `config` + `database.get_setting` | `{settings}` |
| `folders.list` | `outlook_connector` | `{folders}` |
| `outlook.check` | `outlook_com_check` | `{ok, version}` |
| `font.list` | (신규) 폰트 목록 | `{families}` |

### 6.3 Event 전체 목록

| event | 발생 시점 | 소비처 |
|---|---|---|
| `ready` | 사이드카 초기화 완료 | 시작 스플래시 해제 |
| `sync.progress` | 동기화 진행 | 상태바 + 진행 다이얼로그 |
| `sync.plan.progress` | 계획 스캔 진행 | 진행 다이얼로그 |
| `index.progress` | 인덱싱 진행 | 진행 다이얼로그 |
| `log` | 사이드카 로그 (debug) | 개발자 콘솔 |
| `error` | 복구 불가 오류 | 오류 토스트 |

---

## 7. 저장소 구조 (Before → After)

### Before
```
Outlook_AnyFinder/
├── main.py            (718줄, PyQt6 AppController)
├── core/  data/  utils/  workers/
├── ui/                (4,098줄, PyQt6)
└── tests/
```

### After
```
Outlook_AnyFinder/
├── frontend/                        ← ① React
│   ├── src/
│   │   ├── components/
│   │   │   ├── layout/       AppShell, Sidebar, Header, StatusBar
│   │   │   ├── search/       SearchBar, FilterChips, ResultList(virtual)
│   │   │   ├── preview/      MailPreview, AttachmentList
│   │   │   ├── settings/     SettingsDialog (tabs)
│   │   │   └── ui/           Button, Dialog, Toast, Chip, Card (design system)
│   │   ├── contexts/         Reducer, SearchContext, SettingsContext
│   │   ├── hooks/            useIpc, useSearch, useSync, useVirtualList
│   │   ├── styles/           tokens.css, fonts.css, themes.css
│   │   ├── types/            ipc.ts (Command/Event 타입 정의)
│   │   └── utils/
│   ├── package.json
│   └── vite.config.ts
│
├── src-tauri/                       ← ② Tauri Rust Core
│   ├── src/
│   │   ├── main.rs
│   │   ├── lib.rs
│   │   ├── sidecar.rs        ★ 프로세스 생명주기 + JSON Lines 파서
│   │   ├── commands/         search.rs, sync.rs, bookmark.rs, settings.rs
│   │   ├── protocol.rs       Request/Response/Event 타입
│   │   ├── logging.rs        파일 로깅
│   │   └── error.rs
│   ├── resources/sidecar/    ← 사이드카 실행 파일 배치 위치
│   ├── icons/
│   ├── Cargo.toml
│   └── tauri.conf.json
│
├── sidecar/                         ← ③ Python Sidecar
│   ├── __main__.py           ★ 엔트리: 로깅 분리 + IPC 루프
│   ├── ipc.py                JSON Lines 프로토콜
│   ├── dispatcher.py         cmd → handler 라우팅
│   ├── com_worker.py         ★ STA 전담 스레드 + Job Queue
│   ├── handlers/             search.py, sync.py, bookmark.py, settings.py ...
│   └── build_sidecar.ps1     PyInstaller --onedir 래퍼
│
├── core/     data/     utils/       ← ★ 무수정 그대로 재사용
├── tests/                           ← ★ 유지 + IPC 테스트 추가
│
├── legacy_pyqt/                     ← 기존 ui/ main.py 보관 (전환 완료까지)
├── README.md  OPTIMIZATION_REPORT.md  ...
└── MIGRATION_PLAN.md
```

### 빌드 파이프라인 (After)
```powershell
# 1) 사이드카 빌드
powershell -File sidecar\build_sidecar.ps1
#    → src-tauri\resources\sidecar\  (onedir)

# 2) 프론트엔드 + Tauri 번들
cd frontend
pnpm install
pnpm tauri:build
#    → src-tauri\target\release\bundle\nsis\OutLookAnyFinder_0.9.2_x64-setup.exe
```

---

## 8. 단계별 실행 계획 (Phase 0 ~ 5)

### Phase 0 — 준비 및 스파이크 검증 (2~3일)

**목표**: 기술적 불확실성 제거. **전면 전환 전 반드시 통과해야 하는 관문.**

| 작업 | 산출물 | 완료 기준 | 상태 |
|---|---|---|---|
| 0-1 | 브랜치 `migration/react-tauri` 생성, `baseline-v0.9.1.1` 태그 | `git tag` 로 확인 | ⬜ |
| 0-2 | `legacy_pyqt/` 로 기존 UI 이동, `pytest` 재실행 | **198 passed 유지** | ⬜ |
| 0-3 | Rust/Node 툴체인 설치 | `cargo --version`, `pnpm -v` | ⬜ |
| 0-4 | **스파이크 A**: Tauri hello-world + Python 사이드카 echo | IPC 왕복 성공 | ⬜ |
| 0-5 | **스파이크 B**: `pythoncom` STA 전담 스레드 100회 반복 호출 | 100/100 성공, 간헐 오류 0 | ⬜ |
| 0-6 | **스파이크 C**: `search.query` 1건을 IPC 경유로 실행 | 검색 결과 정상 반환 | 🟢 **Python 측 완료** |

**🛑 관문 (Gate)**: 0-4, 0-5, 0-6 중 하나라도 실패하면 **전환을 중단하고 대안 B(위험 대비 대비책)로 전환**합니다.

---

### Phase 1 — IPC 계약 + 사이드카 골격 (1주) — 🟢 **완료**

| 작업 | 내용 | 상태 |
|---|---|---|
| 1-1 | `sidecar/ipc.py` — JSON Lines 읽기/쓰기, `id` 매칭, 에러 래핑 | ✅ |
| 1-2 | `sidecar/__main__.py` — **stdout 완전 분리** (fd 레벨), 파일 로깅 | ✅ |
| 1-3 | `sidecar/dispatcher.py` — cmd 라우팅 테이블 | ✅ |
| 1-4 | `sidecar/com_worker.py` — STA 전담 스레드 + Job Queue | ✅ |
| 1-5 | handlers 이식 — **목표 20개 → 실제 46개 명령 구현** | ✅ 초과 달성 |
| 1-6 | `tests/test_sidecar_ipc.py` — 프로토콜 단위/통합 테스트 | ✅ **169개** |

**완료 기준 — 전부 충족**

| 기준 | 결과 |
|---|---|
| `pytest` 198 passed 유지 | ✅ **367 passed** (198 + 169 신규, 회귀 0) |
| IPC 왕복 정상 | ✅ `dev_client.py --mock --doctor` **23/23 통과** |
| `print()` 오염에도 프로토콜 무결 | ✅ 보호 ON 시 stdout = JSON 3줄 정확히 / OFF 시에도 서버 생존 |
| SIGTERM 정상 종료 | ✅ 좀비 프로세스 0건 |
| DB 손상/오류 시 생존 | ✅ `system.hello` 는 DB 없이도 성공 |

**🪲 Windows 실전 검증에서 발견·수정한 치명 버그 (Python 3.14 / 한국어 Windows)**

| # | 증상 | 근본 원인 | 수정 |
|---|---|---|---|
| 1 | `UnicodeDecodeError: 'cp949' codec can't decode byte 0xec` → **사이드카 즉사** | Python 은 파이프 표준 스트림을 `locale.getpreferredencoding()` 으로 처리. 한국어 Windows = **cp949**. Rust 가 보낸 UTF-8 JSON 을 stdin 에서 읽다 실패. **한글 파라미터(검색어·북마크명·폴더명) 전면 불가** | `stdio_guard.force_utf8_io()` 로 stdin/stdout/stderr 를 UTF-8 강제 (`__main__` STEP 1) |
| 2 | `UnicodeDecodeError` in `subprocess._readerthread` → 테스트 9개 실패 | 동일 원인 (한국어 로그가 cp949 바이트로 stderr 에 출력) | 동일 수정 + 테스트를 바이너리 캡처로 변경 |
| 3 | `AttributeError: 'NoneType' object has no attribute 'splitlines'` | 위 디코딩 실패로 subprocess 가 `stdout=None` 반환 | 테스트를 바이너리로 받아 직접 `errors="replace"` 디코딩 |
| 4 | SIGTERM 테스트 실패 (`비정상 종료 코드: 1`) | Windows 의 `Popen.send_signal(SIGTERM)` 은 `TerminateProcess` 로 매핑되어 **잡을 수 없음** | Windows 분기: `CTRL_BREAK_EVENT`(SIGBREAK 핸들러) 검증 + 종료 여부 확인 |
| 5 | `--noconsole` 빌드 시 stdout/stderr 가 `None` 이 될 위험 | PyInstaller windowed 모드 | 빌드를 `--console` 로 변경, 창 숨김은 Rust `CREATE_NO_WINDOW` 로 |

**추가된 회귀 테스트 (이 버그들이 다시 들어오지 못하게 고정)**

| 테스트 | 고정하는 것 |
|---|---|
| `test_14_utf8_forced_under_cp949_locale` | `PYTHONIOENCODING=cp949:strict` 환경에서 사이드카가 **스스로** UTF-8 을 강제 |
| `test_15_korean_search_response_preserved` | 한글 검색어 → 한글 결과(제목·폴더명) 왕복 보존 |
| `test_16_stderr_logs_are_utf8` | 한국어 로그가 cp949 로 나가지 않음 |
| `test_17_utf8_forced_without_pythonioencoding` | 환경변수 없이도(기본 spawn) UTF-8 |
| `test_18_stdio_guard_unit` | `force_utf8_io()` 가 `cp949 → utf-8` 로 실제 전환 |
| `test_07_shutdown_while_blocked_on_stdin` | stdin 을 **열어둔 채** 종료 요청해도 즉시 종료 (좀비 방지) |
| `test_08_signal_terminates_process` | 신호 후 반드시 정리 (플랫폼별 경로 분리) |

> ★ 회귀 테스트는 `PYTHONIOENCODING` / `PYTHONUTF8` 을 **일부러 제거한 뒤** 실행한다.
> 그래야 사이드카가 스스로 UTF-8 을 강제하는지 진짜로 검증된다.
> Rust 에서 환경변수를 넘겨주는 것은 이중 안전장치일 뿐, 그것에 의존하면 안 된다.

**🪟 Windows 실전 실행에서 추가 확인·수정한 것**

| # | 항목 | 결과 |
|---|---|---|
| 1 | **`pythoncom` STA 스레드 초기화** | ✅ `ComWorker: CoInitialize 완료 (STA)` — 한국어 Windows / Python 3.14 에서 정상. **계획서 리스크 1이 상당 부분 해소** |
| 2 | UTF-8 강제 적용 | ✅ `{'stdin': 'reconfigured', 'stdout': 'reconfigured', 'stderr': 'reconfigured'}` → `utf-8` |
| 3 | 명령 46개 등록 | ✅ 전부 정상 등록 |
| 4 | **PowerShell 따옴표 문제** | ⚠️ Bash 형식 `\"` 이스케이프가 PowerShell 에서 동작하지 않아 `UNKNOWN_COMMAND` 발생 → dev_client 에 **4가지 입력 형식** 도입 |
| 5 | `Popen.creationflags` 속성 없음 (테스트 버그) | ✅ `sidecar_creation_flags` 로 기록 + **stderr drain 스레드** 추가 (파이프 버퍼 블로킹 방지) |
| 6 | `dev_client.py` docstring 이스케이프 경고 | ✅ raw 문자열로 변경, 전 파일 SyntaxWarning 0건 |

**★ dev_client 입력 형식 (PowerShell 대응)**

```powershell
# ✘ 동작 안 함 (Bash 형식)
py sidecar\dev_client.py "search.record {\"keyword\":\"계약서\"}"

# ○ 1. key=value — 따옴표 불필요
py sidecar\dev_client.py search.record keyword=계약서

# ○ 2. 작은따옴표 JSON
py sidecar\dev_client.py search.query '{"query":"보고서","per_page":5}'

# ○ 3. 한 토큰으로
py sidecar\dev_client.py 'search.query {"query":"보고서"}'

# ○ 4. stdin 파이프 (복잡한 JSON)
'{"patch":{"ui":{"theme":"warm-dark"}}}' | py sidecar\dev_client.py --stdin-json settings.set
```

고정 테스트: `TestDevClientArgs` **21개**

**추가로 확보한 것 (계획에 없던 것)**

- `sidecar/dev_client.py` — Rust 없이 테스트하는 REPL/진단/시나리오 도구
- `sidecar/build_sidecar.ps1` — PyInstaller `--onedir` 빌드 + Tauri 리소스 복사
- `sidecar/README.md` — 46개 명령 + 이벤트 + 오류 코드 **IPC 계약서**
- `sidecar/stdio_guard.py` — 3중 stdout 방어 (fd 레벨까지)
- `sidecar/serialize.py` — dataclass → JSON 안전 변환 (예외 불가침)
- 핸들러 이식 과정에서 **기존 로직의 잠재 버그 3건 발견·수정**
  1. `BookmarkManager.delete()` 가 없는 ID 에도 `True` 반환 → 존재 확인 추가
  2. `preview.safe` 가 `RuntimeError: dictionary changed size during iteration` 발생 → `list()` 스냅샷
  3. 다중 폴더 선택 시 AND 결합 → OR 결합으로 수정 (PyQt6 판의 잠재 버그)

**중요**: 이 단계는 **Python만으로 완결**됩니다. Rust 없이 여기서 전부 테스트 가능합니다.
따라서 실패해도 손실이 작고, 성공하면 이후가 결정적으로 쉬워집니다.

**다음 할 일 (Phase 0 잔여 + Phase 2)**
1. Phase 0-1~0-3: 브랜치/태그 생성, 툴체인 설치 (Windows)
2. Phase 0-4: Tauri hello-world + 사이드카 spawn (스파이크 A)
3. Phase 0-5: **실제 Outlook** 대상 `pythoncom` STA 100회 반복 테스트 (스파이크 B) ← **최대 리스크**
4. Phase 2: Rust `sidecar.rs` 작성

---

### Phase 2 — Tauri Rust Core (1.5주)

| 작업 | 내용 |
|---|---|
| 2-1 | `tauri.conf.json` — 창, 크기, CSP, NSIS, 리소스 |
| 2-2 | `sidecar.rs` — spawn / `CREATE_NO_WINDOW` / health-check / 자동 재시작 / 정상 종료 |
| 2-3 | `protocol.rs` — Request/Response/Event (serde) |
| 2-4 | JSON Lines 파서 — 부분 수신 라인 버퍼링, 파싱 실패 방어 |
| 2-5 | `commands/` — 프론트에 노출할 `#[tauri::command]` 20개 |
| 2-6 | 이벤트 브리지 — sidecar event → `app.emit_all()` |
| 2-7 | 트레이, 단일 인스턴스, 창 상태 저장, 파일 로깅 |
| 2-8 | 앱 종료 시 사이드카 graceful shutdown + 강제 kill 폴백 |

**완료 기준**
- ✅ `cargo test` 통과
- ✅ 사이드카 프로세스 강제 종료 시 자동 재기동 확인
- ✅ 앱 종료 후 좀비 프로세스 0건 (`tasklist | findstr Sidecar`)
- ✅ IPC 왕복 지연 **5ms 이하** (로컬 측정)

---

### Phase 3 — React 프론트엔드 (3주) ★ 가장 큰 작업

**3주차 분할**

| 주차 | 작업 |
|---|---|
| 3-1주 | 디자인 토큰 + 디자인 시스템 + App Shell (Sidebar/Header/StatusBar) |
| 3-2주 | 검색바 + 필터칩 + **가상 스크롤 결과 리스트** + 메일 카드 |
| 3-3주 | 미리보기 패널 + 설정 다이얼로그 + 북마크 + 다이얼로그/토스트 |

| 작업 | 내용 |
|---|---|
| 3-1 | `styles/tokens.css` — 색/간격/타이포/그림자/반경 토큰 (3테마) |
| 3-2 | 폰트: **Pretendard Variable** (`@fontsource-variable/pretendard`) + 나눔고딕 폴백 + `font-display: swap` |
| 3-3 | 아이콘: **lucide-react** (벡터, 일관된 stroke) — 현재 QPainter 아이콘 대체 |
| 3-4 | `AppShell` — Sidebar / Header / Main / Preview 4분할 |
| 3-5 | `Sidebar` — 4대 폴더 + 폴더편지함 + 북마크 + 접기(애니메이션, 잔상 없음) |
| 3-6 | `SearchBar` + `FilterChips` (받은/보낸/임시/지운/폴더편지함 — 2회 클릭 버그 원천 차단) |
| 3-7 | **`ResultList` — `@tanstack/react-virtual` 가상 스크롤** |
| 3-8 | `MailCard` — 첨부파일 배지, 하이라이트(safe HTML), 호버 테두리 |
| 3-9 | `MailPreview` — HTML 안전 렌더링 (sanitize 필수) |
| 3-10 | `SettingsDialog` — 탭, 테마 3종 실시간 미리보기 |
| 3-11 | Toast / Dialog / Modal 컴포넌트 (디자인 시스템 기반) |
| 3-12 | 키보드 단축키, 포커스 링, 접근성 |

**완료 기준**
- ✅ 4가지 기존 문제 **전부 해결** (폰트/그래픽, 테마 대비, 스크롤, 잔상)
- ✅ 가상 스크롤: **10,000건 리스트 60fps 스크롤** (DevTools Performance 측정)
- ✅ 테마 3종 전환 시 대비(WCAG AA) 자동 검증 통과
- ✅ Lighthouse 접근성 90점 이상

---

### Phase 4 — 기능 동등성(Parity) 확보 및 데이터 마이그레이션 (1주)

| 작업 | 내용 |
|---|---|
| 4-1 | **Parity 체크리스트** 작성 — PyQt6 버전의 모든 기능 1:1 대조 |
| 4-2 | DB 경로 동일 사용 → **기존 인덱스 그대로 활용** (재색인 불필요) |
| 4-3 | 설정 마이그레이션 (`config.json` → 위치 유지, 키 매핑) |
| 4-4 | 사이드카·프론트 버전 불일치 감지 및 안내 |
| 4-5 | 기능별 수동 테스트 시나리오 20종 실행 |
| 4-6 | 롤백 절차 문서화 (문제 시 PyQt6 빌드로 즉시 복귀) |

**완료 기준**
- ✅ 체크리스트 100% 통과
- ✅ 기존 사용자 DB로 **재색인 없이** 검색 동작
- ✅ 롤백 스크립트 실제 실행 검증

---

### Phase 5 — 패키징, 서명, 배포 (1~1.5주)

| 작업 | 내용 |
|---|---|
| 5-1 | `sidecar/build_sidecar.ps1` — PyInstaller `--onedir` + 리소스 번들 |
| 5-2 | `src-tauri/resources/sidecar/` 자동 배치 |
| 5-3 | `tauri build` → NSIS 설치 파일 (Korean 언어, currentUser) |
| 5-4 | WebView2 부트스트랩 (`offlineInstaller`) |
| 5-5 | 코드 서명 (DocuFinder의 `create-cert.ps1` 참고) |
| 5-6 | 자동 업데이트 (`tauri-plugin-updater` + GitHub Releases) |
| 5-7 | 클린 VM 설치 테스트 (Windows 10 / 11, Outlook 2016 / 365) |
| 5-8 | 문서 갱신: `README.md`, `실행_가이드.md`, `MIGRATION_PLAN.md` |

**완료 기준**
- ✅ 클린 VM에서 설치 → 첫 실행 → Outlook 동기화 → 검색 성공
- ✅ 백신 오탐 0건 (Windows Defender / V3)
- ✅ 좀비 프로세스 0건, 설치/제거 정상

---

### 전체 일정 요약

| Phase | 내용 | 집중 투입 | 파트타임 | 진행 |
|---|---|---|---|---|
| 0 | 준비 + 스파이크 | 3일 | 1주 | 🟡 부분 (0-6 완료) |
| 1 | IPC + 사이드카 | 4일 | 1주 | 🟢 **완료** |
| 2 | Tauri Rust | 1주 | 1.5주 | ⬜ |
| 3 | React UI | **2주** | **3주** | ⬜ |
| 4 | Parity | 4일 | 1주 | ⬜ |
| 5 | 패키징/배포 | 5일 | 1주 | ⬜ |
| **합계** | | **약 5주** | **약 9주** | **약 25%** |

**Phase 3(React UI) 이 전체의 40%** 입니다. 여기가 승부처입니다.

---

## 9. 성능 기대치 — 정직한 수치

| 항목 | 현재 (PyQt6) | 전환 후 (React + Tauri) | 판정 |
|---|---|---|---|
| 앱 시작 → 창 표시 | 3~6초 (PyInstaller onedir) | **0.3~0.8초** (Tauri 셸) | 🟢 **5~10배 개선** |
| 앱 시작 → 검색 가능 | 3~6초 | 2~4초 (사이드카 백그라운드) | 🟢 소폭 개선 |
| 10,000건 리스트 스크롤 | 끊김 (60fps 미달) | **60fps** (가상 스크롤) | 🟢 **대폭 개선** |
| 검색 응답 시간 | 40~80ms | 45~85ms (+IPC 3ms) | 🟡 **차이 없음** |
| Outlook 동기화 속도 | COM 바운드 | COM 바운드 | ⚪ **변화 없음** |
| 동기화 중 검색 가능? | 제한적 | **가능** (스레드 분리) | 🟢 개선 |
| 메모리 사용 | ~180MB | ~200MB (WebView2 공유) | 🟡 소폭 증가 |
| 패키지 크기 | ~90MB | ~120MB | 🟡 소폭 증가 |
| UI 커스터마이즈 자유도 | 낮음 (QSS 한계) | **매우 높음** (완전한 CSS) | 🟢 **핵심 이득** |
| 개발 복잡도 | 낮음 | **높음** (3개 툴체인) | 🔴 악화 |

> ⚠️ **반드시 이해해야 할 점**: "프로그램 속도 개선"의 실체는 **UI 렌더링과 시작 속도**입니다.
> **Outlook에서 메일을 읽어오는 동기화 속도는 변하지 않습니다.** 그 병목은 Outlook COM 자체입니다.
> 만약 사용자가 느끼는 "느림"이 동기화라면, Tauri 전환으로는 해결되지 않습니다.
> 대신 **동기화 중에도 UI가 멈추지 않는 것**이 체감 개선의 핵심이 됩니다.

---

## 10. 대안 비교 — 3가지 선택지

| | **A. 유지 (PyQt6 개선)** | **B. 하이브리드** | **C. 전면 전환 (제안)** |
|---|---|---|---|
| **내용** | 현 구조 유지 + UI 패치 | PyQt6 유지 + 사이드카만 분리 | React + Tauri + Sidecar |
| **기간** | 1~2주 | 3~4주 | 5~9주 |
| **폰트/그래픽 문제** | △ 부분적 완화 | △ 변화 없음 | ✅ **완전 해결** |
| **테마 대비 버그** | △ 재발 가능 | △ 재발 가능 | ✅ **구조적 해결** |
| **대량 리스트 성능** | ❌ 한계 | ❌ 한계 | ✅ **해결** |
| **시작 속도** | ❌ 그대로 | ❌ 그대로 | ✅ **개선** |
| **동기화 속도** | ⚪ 동일 | ⚪ 동일 | ⚪ 동일 |
| **유지보수 난이도** | 쉬움 | 중간 | **어려움** |
| **리스크** | 낮음 | 낮음 | **중~높음** |

**권장**: **C를 선택하되 Phase 0~1을 먼저 통과**하세요.
Phase 0~1은 Python만으로 완결되고, 실패해도 손실이 작습니다.
그리고 Phase 1까지만 해도 **테스트 가능한 사이드카 자산**이 남아 대안 B가 자동 확보됩니다.
즉 **Phase 0~1은 어느 쪽을 선택해도 손해가 없는 투자**입니다.

---

## 11. 즉시 실행 명령 (Windows PowerShell)

### 11-1. 준비 및 백업

```powershell
cd C:\Arena\Outlook_AnyFinder

# 1) 현재 상태 확인 (미커밋 변경 있는지)
git status

# 2) 기준점 태그
git tag -a baseline-v0.9.1.1 -m "Stable baseline: 198 tests passed"
git push origin baseline-v0.9.1.1

# 3) 전환 브랜치 생성
git checkout -b migration/react-tauri
git push -u origin migration/react-tauri

# 4) DB 백업 (전환 중 손상 대비 — 필수)
copy "$env:USERPROFILE\.outlook_anyfinder\anyfinder.db" `
     "$env:USERPROFILE\.outlook_anyfinder\anyfinder.db.bak-v0.9.1"
```

### 11-2. 툴체인 설치

```powershell
# Rust (MSVC 툴체인)
winget install Rustlang.Rustup
rustup default stable-msvc
rustc --version
cargo --version

# Node + pnpm
winget install OpenJS.NodeJS.LTS
npm install -g pnpm
pnpm -v

# Tauri 빌드 전제 (Visual Studio Build Tools - C++ 데스크톱 개발)
winget install Microsoft.VisualStudio.2022.BuildTools
# 설치 시 "Desktop development with C++" 워크로드 체크 필수

# WebView2 (Windows 11은 기본 포함, 10은 확인 필요)
winget install Microsoft.EdgeWebView2Runtime
```

### 11-3. PyQt6 UI를 legacy로 이동 (Phase 0-2)

```powershell
cd C:\Arena\Outlook_AnyFinder
mkdir legacy_pyqt
move ui legacy_pyqt\ui
move main.py legacy_pyqt\main.py
git add -A
git commit -m "refactor: move PyQt6 UI to legacy_pyqt (Phase 0)"

# 회귀 테스트 — 198 passed 유지 확인
py -m pytest tests/ -q --tb=line
```

### 11-4. 스파이크 검증 (Phase 0-4~6)

```powershell
# 툴체인 확인
cargo --version; pnpm -v; py --version

# Tauri 프로젝트 생성 (frontend 폴더에)
cd C:\Arena\Outlook_AnyFinder
pnpm create tauri-app frontend --template react-ts
cd frontend
pnpm install
pnpm tauri dev     # 창이 뜨면 스파이크 A 성공

# Rust 의존성 초기 추가
cd ..\frontend\src-tauri
cargo add tauri-plugin-single-instance tauri-plugin-window-state
cargo add serde --features derive
cargo add serde_json
```

> ⚠️ 첫 `cargo build` 는 5~15분 걸립니다 (전체 의존성 컴파일). 정상입니다.

---

## 12. Go / No-Go 판단 체크리스트

전환을 시작하기 전 아래를 확인하세요.

### Go 조건 (모두 충족 시 진행)
- [ ] `pytest` **198 passed** 현재 통과 중
- [ ] DB 백업 완료 (`anyfinder.db.bak-v0.9.1`)
- [ ] Rust + Node 툴체인 설치 완료
- [ ] **Phase 0 스파이크 3종 모두 성공**
- [ ] 전환 기간 동안 신규 기능 요구를 **2개월간 동결**할 수 있음
- [ ] 현재 겪는 불편(폰트/그래픽/스크롤)이 **UI 문제**이며 동기화 문제가 아님을 확인

### No-Go 조건 (하나라도 해당 시 대안 B 검토)
- [ ] 불만의 핵심이 "Outlook 동기화가 느리다" → **Tauri로 해결 안 됨**
- [ ] 전환 기간 중 신규 기능 요구가 계속 들어옴
- [ ] Python 3.13 + pywin32 + PyInstaller 조합에서 COM 문제 발생
- [ ] Rust 빌드 환경 구성에 2일 이상 소요

---

## 부록 A. 참고 레퍼런스 (이미 로컬에 확보됨)

| 파일 | 참고할 내용 |
|---|---|
| `Docufinder/src-tauri/tauri.conf.json` | Tauri 2 설정 전체 (NSIS, CSP, 리소스, updater) |
| `Docufinder/src-tauri/Cargo.toml` | Rust 의존성 구성 |
| `Docufinder/scripts/bundle-kordoc.ps1` | **외부 런타임 리소스 번들 패턴** ← 사이드카에 직접 응용 |
| `Docufinder/scripts/create-cert.ps1` | 코드 서명 |
| `Docufinder/scripts/download-vcredist.ps1` | VC++ 재배포판 처리 |
| `Docufinder/src/styles/variables.css` | CSS 디자인 토큰 |
| `Docufinder/src/components/ui/*` | Button / Modal / Toast 컴포넌트 |
| `Docufinder/src/components/layout/*` | AppShell / Sidebar / Header |
| `Docufinder/package.json` | Vite + Tauri 스크립트 구성 |

## 부록 B. 정확한 기술 스택 (고정 버전)

```jsonc
// frontend/package.json
{
  "dependencies": {
    "@tauri-apps/api": "^2.9.1",
    "@tauri-apps/plugin-dialog": "^2.6.0",
    "@tauri-apps/plugin-updater": "^2.9.0",
    "@tanstack/react-virtual": "^3.13.0",   // ★ 가상 스크롤
    "lucide-react": "^0.469.0",              // ★ 벡터 아이콘
    "clsx": "^2.1.1",
    "react": "^19.2.3",
    "react-dom": "^19.2.3"
  },
  "devDependencies": {
    "@tauri-apps/cli": "^2.9.6",
    "@tailwindcss/vite": "^4.1.18",
    "tailwindcss": "^4.1.18",
    "typescript": "^5.9.3",
    "vite": "^7.3.2",
    "@vitejs/plugin-react": "^5.1.2"
  }
}
```

```toml
# src-tauri/Cargo.toml
[dependencies]
tauri = { version = "^2.10", features = ["tray-icon"] }
tauri-plugin-dialog = "^2.6"
tauri-plugin-single-instance = "^2"
tauri-plugin-window-state = "^2.4"
tauri-plugin-updater = "^2.9"
tauri-plugin-process = "^2.3"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio = { version = "1", features = ["rt-multi-thread", "macros", "time", "sync", "process", "fs"] }
chrono = "0.4"
thiserror = "2"
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }
```

> **주의**: Rust는 사이드카 **프로세스 관리 + IPC 중계**만 담당합니다.
> DocuFinder처럼 검색/파싱을 Rust로 재구현하지 마세요.
> 그건 6개월 이상 걸리며, 이 프로젝트에서는 이득이 없습니다.

---

## 부록 C. 저장소 반영 현황 (2026-10-02, Arena 세션)

이 문서는 로컬(Windows) 작업 기준의 진행 상태를 포함한다. GitHub 저장소 반영 기준 실제 상태는 다음과 같다.

| Phase | 저장소 반영 상태 |
|---|---|
| 0-1 | ✅ `baseline-v0.9.1.1` 태그 원격 존재 (b6ebc46 가리킴). 브랜치는 세션 브랜치 `arena/01a0faf7-outlook-anyfinder`에서 진행 |
| 0-2 | ✅ `ui/` + `main.py` → `legacy_pyqt/` 이동 완료. pytest **198 passed 유지**. legacy 빌드 스크립트(spec/build_exe/build_release) 경로 갱신 |
| 0-3 | ⬜ Rust 툴체인은 Windows PC에서 설치 필요 (Linux 개발 샌드박스는 Node v22만 가용) |
| 0-4/0-5 | ⬜ 스파이크 A(Tauri hello-world)/B(실 Outlook STA 100회)는 **Windows 실기기 필요** |
| 0-6 | ✅ 스파이크 C — `search.query` IPC 경유 실행 성공 (Linux/Mock, 통합 테스트로 고정) |
| 1 | ✅ **저장소 기준으로 계약 재구현 완료**: 명령 40개, `sidecar/` 15개 파일, `tests/test_sidecar_ipc.py` 91개. 전체 **289 passed** (198+91, 회귀 0), `dev_client --doctor` **34/34**. 계획서 Phase 1의 Windows 버그 수정(cp949 UTF-8 강제, SIGBREAK, fd 레벨 stdout 보호, stderr drain)과 잠재 버그 3건(북마크 삭제 반환값, dict 스냅샷, 다중 폴더 OR) 전부 반영. ※ 로컬 Windows에 별도 Phase 1 구현이 있다면 이 저장소 버전과 대조 필요 |
| 2 | ✅ 코드 완성 — **컴파일 미검증(샌드박스 Rust 툴체인 차단, Windows 검증 대기)**: `src-tauri/` Rust 모듈 8개(lib/sidecar/protocol/commands/tray/logging/error/main) + `tauri.conf.json`(NSIS·Korean/English·offlineInstaller) + capabilities + 아이콘(PNG/ICO, 표준 라이브러리 생성기). 사이드카 생명주기 전체(spawn 플래그·reader 방어 파서·15초 헬스체크/재시작 5회 캡·shutdown→CTRL_BREAK→kill), 단일 인스턴스, 트레이(열기/동기화/종료), 창 상태 기억. 절차는 `src-tauri/README.md` |
| 3 | ✅ `frontend/` — React 19.2 + Vite 7.3 + TS 5.9 + Tailwind 4 + @tanstack/react-virtual + lucide + Pretendard. 화면: 검색바(자동완성·"정확한 단어만")/필터칩(폴더 OR·첨부·기간·정렬)/가상 리스트+페이지네이션/미리보기 패널/사이드바(폴더·북마크·통계)/설정 5탭(데이터 관리 포함)/폴더 선택 동기화(plan→승인→execute+진행·취소)/첫 실 온보딩/토스트/상태바(자동 동기화 카운트다운)/3테마(dark·light·warm-dark). IPC 트랜스포트 추상화로 **Tauri 없이 브라우저 개발 가능**(`dev_bridge.py`+vite 프록시). `tsc --noEmit`·`vite build` 그린, jsdom 스모크(`npm run smoke`, 실 브리지 경유) PASS |
| 4~5 | ⬜ 미착수 — 패리티 검증/데이터 마이그레이션 리허설, NSIS 패키징·서명·업데이터 |

추가로 반영된 것:
- `sync_meta.schema_version` 도입 (사이드카가 DB 열 때 자동 기록, `db.schema_version` 명령) — 구 REVIEW_REPORT §4.3 및 본 계획 리스크 4 대응
- `db.backup` 명령 (sqlite3 backup API, WAL 안전) — 리스크 4의 마이그레이션 전 백업 대응
- Mock 고정 날짜(2026-05-27) 타임밤 방지: 테스트/doctor는 기간 필터(range_months>0)를 쓰지 않도록 고정
- **Phase 2/3 추가분**: 명령 40→**42** (`db.clear_history`, `db.reset_all{confirm:true}` — 설정>데이터 탭), 사이드카 테스트 91→**93** (전체 291 passed)
- 브라우저 개발 모드: `frontend/dev_bridge.py`(표준 라이브러리 HTTP+SSE 브리지, 127.0.0.1:8765, mock 기본) + vite `/sidecar` 프록시 — Rust 없이 UI 전체 개발/스모크 가능
- 부록 B 핀 대비 실제 확정: `@vitejs/plugin-react` 5.x (6.x는 Vite 8 전용), Pretendard는 `@fontsource/pretendard`(정적) — fontsource에 variable 패키지가 없음, lucide-react 0.469 고정(1.x 회피)

**의도적 편차 (사용자 검토 요청)** — 상세 근거는 `src-tauri/README.md` 말미:
1. 계획서의 타입 명시 `commands/{search,mail,index,sync,system}.rs` 대신 **제네릭 패스스루 `sidecar_request` 1개** — 계약 이중화 방지, 타입 안정성은 TS 래퍼(`frontend/src/lib/api.ts`)에서 확보
2. `tauri-plugin-log` 대신 최소 std 파일 로깅 (`desktop.log`)
3. **창 닫기 = 트레이 숨김** (legacy는 닫기=종료) — 트레이 배경 동기화를 위한 상주 정책 변경
4. 미리보기는 `preview.mail`(평문 본문) 계약 사용 — HTML iframe 렌더 불필요(XSS 공격면 제거)

**문서 끝.**
