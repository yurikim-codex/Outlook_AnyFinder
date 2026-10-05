# src-tauri — Rust 코어 (Phase 2)

Tauri 2 기반 데스크톱 셸. **프로세스 관리 + IPC 중계 + 윈도우/트레이만** 담당한다.
비즈니스 로직(SQL·검색·Outlook COM·동기화 계획)은 전부 Python 사이드카(`sidecar/`)에 있다.

```
React UI ──invoke("sidecar_request")──▶ Rust 코어 ──stdin JSON Lines──▶ Python 사이드카
   ▲                                        │                              │
   └──────listen("sidecar://event")─────────┘◀─────stdout JSON Lines───────┘
```

## 구조

| 파일 | 역할 |
|---|---|
| `src/lib.rs` | 앱 조립 — 플러그인(단일 인스턴스·윈도우 상태), setup(로깅·사이드카·트레이), 닫기=트레이 숨김, Exit 시 사이드카 정리 |
| `src/sidecar.rs` | 사이드카 생명주기 — spawn(CREATE_NO_WINDOW+NEW_PROCESS_GROUP), reader 스레드(방어 파싱+id 매칭+이벤트 브리지), 헬스 모니터(15초 ping, 3회 실패 재시작, 최대 5회), graceful shutdown(shutdown→3초→CTRL_BREAK→kill) |
| `src/protocol.rs` | JSON Lines 파서(단위 테스트 포함) — 이벤트/응답/쓰레기 줄 분류, panic 없음 |
| `src/commands.rs` | Tauri 명령 4개 — `sidecar_request`(제네릭 패스스루), `sidecar_status`, `sidecar_restart`, `frontend_log` |
| `src/tray.rs` | 트레이 — 열기 / 지금 동기화(`tray://sync` 이벤트 브로드캐스트) / 종료 |
| `src/logging.rs` | 파일 로깅 `{앱 로그}/desktop.log` (5MB 로테이션) — 사이드카 stderr도 여기로 |
| `src/error.rs` | `CommandError{code,message}` — TS의 `SidecarError`와 동일한 모양 |
| `icons/` | `generate_icons.py`(표준 라이브러리)로 생성한 PNG/ICO — 필요시 `npx tauri icon`으로 교체 |

## 사이드카 실행 파일 해석 순서

1. `ANYFINDER_SIDECAR_CMD` 환경변수 (개발 오버라이드)
2. `{리소스}/resources/sidecar/OutlookAnyFinderSidecar.exe` — 배포본 (`bundle.resources`로 포함)
3. `{repo}/dist/OutlookAnyFinderSidecar/...` — 로컬 PyInstaller 빌드 (`sidecar/build_sidecar.ps1`)
4. `py -3 -m sidecar` (cwd=저장소 루트) — 개발 폴백. Mock은 `ANYFINDER_MOCK=1` 또는 비Windows 자동

## Windows 검증 절차 (개발 머신)

이 샌드박스는 Rust 툴체인 설치 차단(SSL)으로 **컴파일 미검증** 상태다. 아래 순서로 검증한다.

```powershell
# 0) 사전: Rust stable + WebView2 런타임 + Node 22 + Python 3.11+
rustup default stable

# 1) 사이드카 바이너리 빌드 (리소스로 복사됨)
powershell -File sidecar\build_sidecar.ps1

# 2) 개발 실행 (Vite dev + Rust 디버그 빌드 + 목 사이드카)
$env:ANYFINDER_MOCK="1"
npm install            # 루트 (Tauri CLI)
npm install --prefix frontend
npm run dev            # = tauri dev

# 3) 단위 테스트 (Rust)
cargo test --manifest-path src-tauri\Cargo.toml

# 4) 릴리즈 빌드 (NSIS 설치본)
npm run build          # = tauri build → src-tauri\target\release\bundle\nsis\*.exe
```

검증 체크리스트:
- [ ] 기동 시 콘솔 창 없음 (CREATE_NO_WINDOW)
- [ ] 창 표시와 동시에 사이드카 spawn (직렬 대기 없음) — 작업관리자에 `OutlookAnyFinderSidecar.exe`
- [ ] 검색 동작 중 사이드카 강제 종료(`taskkill`) → 15초 내 자동 재시작 + UI 복구
- [ ] 앱 종료 시 사이드카 프로세스 잔존 0건 (종료 후 작업관리자 확인)
- [ ] 트레이 "지금 동기화" → 창 열리며 동기화 시작
- [ ] 두 번째 exe 실행 → 기존 창에만 포커스 (단일 인스턴스)
- [ ] 창 닫기 → 트레이로 숨김, 트레이 "종료"만 실제 종료
- [ ] 설치본(NSIS) 설치/제거 정상, Korean/English 언어 선택

## 계획서 대비 의도적 편차 (승인 검토용)

1. **타입 명시 commands/{search,mail,...}.rs 대신 제네릭 패스스루 1개** (`sidecar_request`).
   근거: IPC 계약서(`sidecar/README.md`)가 단일 진실 공급원이고 명령이 42개→계속 추가되므로,
   Rust 래퍼는 중복 계약이 된다. 타입 안정성은 TS(`frontend/src/lib/api.ts`)에서 확보.
2. **tauri-plugin-log 대신 최소 std 파일 로깅** — 의존성과 설정 표면 감소, 로테이션 5MB×1 충분.
3. **창 닫기 = 트레이 숨김** — 트레이 "지금 동기화"가 배경 동작하려면 프로세스 상주가 필요.
   (legacy PyQt6판은 닫기=종료였음 — 정책 변경이므로 사용자 확인 권장)
4. **아이콘**: `npx tauri icon` 산출물 대신 표준 라이브러리 생성기 커밋 (오프라인 재현 가능).
