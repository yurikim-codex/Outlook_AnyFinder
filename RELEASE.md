# 릴리즈 절차 — NSIS 설치본 + 서명 + 자동 업데이트 (Phase 5)

> 대상: Windows 릴리스 관리자. 모든 명령은 저장소 루트에서 실행.
> 소요: 초회 약 30분(인증서/키 생성 포함), 이후 회당 약 10분.

## 0. 버전 범프

```powershell
node tools\bump-version.mjs 1.0.1     # Cargo.toml/tauri.conf/version.ts/__init__.py 일괄
git add -A; git commit -m "release: v1.0.1"; git push
```

## 1. 사이드카 빌드 (5-1/5-2)

```powershell
powershell -ExecutionPolicy Bypass -File sidecar\build_sidecar.ps1
# → dist\OutlookAnyFinderSidecar\ (onedir+console) → src-tauri\resources\sidecar\ 자동 복사
# → 빌드된 exe로 --mock --version 스모크 자동 실행
```

## 2. 업데이터 키 (최초 1회, 5-6)

```powershell
node tools\gen-updater-keys.mjs       # tools\updater-keys\ 키쌍 + conf pubkey 자동 반영
# 비밀키(updater.key)는 릴리스 관리자만 보관 — gitignore 됨
# 빌드 시 환경변수:
$env:TAURI_SIGNING_PRIVATE_KEY = Get-Content tools\updater-keys\updater.key -Raw
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ""
```

## 3. Tauri 빌드 (5-3/5-4)

```powershell
npm install                            # 루트 (Tauri CLI)
npm install --prefix frontend
npm run build                          # = tauri build
# 산출물 (빌드가 만드는 것):
#   src-tauri\target\release\bundle\nsis\OutLook AnyFinder_1.0.1_x64-setup.exe
#   src-tauri\target\release\bundle\nsis\*.exe.sig   (업데이터 서명)
node tools\make-latest-json.mjs        # latest.json은 별도 생성 (Tauri v2 CLI는 안 만듦)
# WebView2: offlineInstaller 번들 포함 (사내 망오프라인 VM 대비 → 설치본 ~234MB 정상)
```

## 4. 코드 서명 (5-5)

```powershell
powershell -ExecutionPolicy Bypass -File tools\create-cert.ps1   # 최초 1회 (사내 자기서명)
npm run build   # 빌드 중 signCommand(tools\sign-one.ps1)가 모든 바이너리+설치본 자동 서명
```

- **서명은 빌드 내부에서 수행**(`bundle.windows.signCommand`) — 업데이터 `latest.json`/`.sig`와 해시 일관성 보장. 빌드 후 수동 서명 금지(업데이트 검증 실패 원인).
- 인증서 없는 개발 빌드는 sign-one.ps1이 SKIP하고 정상 진행.
- 대외 배포 시 상용 코드서명 인증서로 교체 (`$env:SIGN_PFX`, `$env:SIGN_PASSWORD`) — 자기서명은 SmartScreen 경고 가능.
- `sesung-codesign.cer`를 사내 PC "신뢰할 수 있는 게시자"에 배포하면 경고 해소.
- 개별 재서명 필요 시에만 `tools\sign.ps1` 사용 (이 경우 업데이터 sig 재생성 필수: `npx tauri signer sign <exe> -k tools\updater-keys\updater.key` 후 latest.json signature 교체).

## 5. GitHub Releases 배포 (5-6)

1. GitHub → Releases → Draft → 태그 `v1.0.1`
2. 업로드: `*-setup.exe`, `latest.json`, `*.exe.sig` (**셋 다 필수** — 업데이터는 latest.json+sig 검증)
3. Publish → 앱 내 설정>업데이트에서 확인 가능해짐 (엔드포인트: releases/latest/download/latest.json)

## 6. 클린 VM 검증 (5-7)

`docs/VM_TEST_CHECKLIST.md` 전체 항목 수행 — 설치→첫 실행→동기화→검색→업데이트→제거→데이터 보존→좀비 0건.

## 7. 롤백 경로

문제 시 `ROLLBACK.md` + `tools\rollback_to_legacy.ps1` — 데이터 공유라 재색인 없음.

## 체크리스트 (릴리스 차단 조건)

- [ ] 사이드카 exe 스모크(`--mock --version`) 통과
- [ ] `tauri build` 경고 0 (conf 스키마/리소스 누락 없음)
- [ ] 서명 3종 완료 + `signtool verify /pa` 통과
- [ ] latest.json의 version == 설치본 version
- [ ] VM 체크리스트 100% (백신 오탐 0, 좀비 0 포함)
