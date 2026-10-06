# Windows 실기 검증 런북 (한 번에 복사-붙여넣기용)

> 대상: 개발자 Windows PC (Rust stable + Node 22 + Python 3.11+ + Outlook 설치).
> 순서대로 실행하고 각 단계의 ✅/❌을 이 파일 하단 기록란에 남기세요. 전체 예상 40~60분.
> 모든 명령은 **저장소 루트**에서. 브랜치: `arena/01a0faf7-outlook-anyfinder` (최신 pull 우선).

## 0. 준비 (1회)

```powershell
git pull origin arena/01a0faf7-outlook-anyfinder
rustup default stable
rustc --version; node --version; python --version
npm install                      # 루트 (Tauri CLI)
npm install --prefix frontend
pip install -r requirements.txt  # 또는 venv
```

## 1. Rust 컴파일 + 단위 테스트 (스파이크 A 포함) — 10분

```powershell
cargo test --manifest-path src-tauri\Cargo.toml
# 기대: protocol.rs 단위 테스트 전부 pass, 경고 0
cargo build --manifest-path src-tauri\Cargo.toml
# ❌ 컴파일 오류 시: 오류 메시지 전체를 이슈/세션에 첨부 (샌드박스는 미검증 상태였음)
```

- [ ] 1-1 cargo test pass
- [ ] 1-2 cargo build warnings 0

## 2. 사이드카 바이너리 + 리소스 배치 (5-1/5-2) — 5분

```powershell
powershell -ExecutionPolicy Bypass -File sidecar\build_sidecar.ps1
# 기대: "Build OK ... MB" + "Smoke test OK" + src-tauri\resources\sidecar\ 채워짐
```

- [ ] 2-1 exe 스모크 OK  - [ ] 2-2 리소스 복사 확인

## 3. Tauri 개발 실행 (스파이크 B는 4번과 함께) — 10분

```powershell
$env:ANYFINDER_MOCK="1"
npm run dev
```

- [ ] 3-1 창 ≤1초 표시, "사이드카 기동 중" 배너 → 자동 해제
- [ ] 3-2 작업관리자: OutlookAnyFinderSidecar.exe 1건, **콘솔 창 없음**
- [ ] 3-3 검색 `견적서` 결과 노출 / 미리보기 본문 표시
- [ ] 3-4 사이드카 taskkill → 15초 내 자동 재시작 + UI 복구 (S17)
- [ ] 3-5 창 닫기 → 트레이 숨김 / 트레이 "지금 동기화" → 동기화 시작 (S18)
- [ ] 3-6 두 번째 `npm run dev` 실행 → 기존 창 포커스만 (단일 인스턴스, S19)
- [ ] 3-7 트레이 "종료" → 사이드카 포함 프로세스 0건 (좀비 0)
- [ ] 3-0(선택) 원샷 자동 검증: `powershell -ExecutionPolicy Bypass -File tools\win_dev_check.ps1`
      — pytest·tsc·build·브리지/Vite·smoke·시나리오·프로브·cargo test를 순차 실행 후 요약 (실패 시 exit 1)
- [ ] 3-8 IPC 런타임 프로브: 개발 브리지 띄운 상태(mock)에서 `python tools/contract_probe.py` → `PROBE_OK`
      (43개 명령 전수 호출, INTERNAL/PARSE_ERROR/크래시 0건 확인 — Windows 사이드카 빌드 동일 검증)

## 4. 실 Outlook 스파이크 B + 실데이터 패리티 — 10분

준비 (실모드는 pywin32(COM) 필수 — Python 3.14용 wheel 존재 확인됨, PyInstaller 6.22도 3.14 지원):

```powershell
python -m pip --version          # 실패 시: python -m ensurepip --upgrade
python -m pip install pywin32 pyinstaller
python -c "import win32com.client; print('pywin32 OK')"
```

사이드카 기동 경로 확인 — `npm run dev`는 아래 순서로 사이드카를 찾는다 (src-tauri/src/sidecar.rs):
1. `ANYFINDER_SIDECAR_CMD` 환경변수 2. 번들 리소스 exe (Step 2 수행 시)
3. `dist\OutlookAnyFinderSidecar\...exe` 4. 폴백 `py -3 -m sidecar` (저장소 루트)
→ Step 2를 수행했으면 빌드된 exe가 쓰이고, 안 했으면 폴백으로 dev Python이 사용된다
(어느 쪽이든 pywin32 필요: exe는 번들, 폴백은 pip 설치분).

```powershell
Remove-Item Env:ANYFINDER_MOCK -ErrorAction SilentlyContinue
npm run dev
```

- [ ] 4-1 outlook.check available=true (COM 연결)
- [ ] 4-2 첫 실행 다이얼로그 → 실 메일 인덱싱 (진행률 이벤트)
- [ ] 4-3 **기존 ~/.outlook_anyfinder DB가 있으면 재색인 없이 즉시 검색** (4-2 핵심)
- [ ] 4-4 폴더 동기화 plan 수치 ↔ Outlook 실 변경 일치 (S16)
- [ ] 4-5 "Outlook에서 열기" / "내보내기" 동작 (S12)
- [ ] 4-6 COM 100회 호출 안정성: 동기화 2회 연속 수행 (에러 0) — 스파이크 B

## 5. 릴리즈 빌드 + 서명 + 업데이터 (Phase 5 실물) — 15분

```powershell
node tools\bump-version.mjs 1.0.0        # 이미 1.0.0이면 변경 없음 확인용
node tools\gen-updater-keys.mjs          # 최초 1회 (pubkey conf 반영)
powershell -ExecutionPolicy Bypass -File tools\create-cert.ps1
$env:TAURI_SIGNING_PRIVATE_KEY = Get-Content tools\updater-keys\updater.key -Raw
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ""
npm run build
# 기대: bundle\nsis\*setup.exe + latest.json + .sig, 빌드 로그에 "[sign-one] ✔" 3회
```

- [ ] 5-1 NSIS 설치본 생성
- [ ] 5-2 서명 로그 3회 (sidecar/셸/설치본) — cert 없으면 SKIP 경고도 허용(첫 회는 cert 생성 후)
- [ ] 5-3 latest.json version == 1.0.0
- [ ] 5-4 설치본 더블클릭 설치 → VM 체크리스트 A그룹 신속 확인
- [ ] 5-5 설정>업데이트>확인 → "최신 버전" (Release 미업로드 상태이므로 정상)

## 6. 롤백 드릴 (S20) — 5분

```powershell
.venv\Scripts\python tools\rollback_check.py     # 또는 py -3
powershell -ExecutionPolicy Bypass -File tools\rollback_to_legacy.ps1 -SkipBuild
# legacy 창이 뜨고 기존 인덱스로 검색 되는지 확인 후 종료
# 복귀: 설치본 재실행 → 재색인 없이 검색
```

- [ ] 6-1 rollback_check 0  - [ ] 6-2 legacy 동작  - [ ] 6-3 신버전 복귀 후 검색

## 기록

| 단계 | 결과 | 비고/오류 메시지 |
|---|---|---|
| 1 | | |
| 2 | | |
| 3 | | |
| 4 | | |
| 5 | | |
| 6 | | |

> ❌ 항목은 명령/오류 로그(`desktop.log`+`sidecar.log` 쌍)와 함께 세션에 전달하세요.
