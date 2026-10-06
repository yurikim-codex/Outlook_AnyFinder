# Release Notes v1.0.0 (초안 — Track B Windows 검증 후 확정)

> 상태: **초안**. Windows 검증(런북 Step 0~6)과 VM 체크리스트 통과 후 확정·배포.
> 배포 절차는 `RELEASE.md`, 사용자 안내는 `실행_가이드.md` §23 참고.

## 개요

OutLook AnyFinder **Ver 0.9 → 1.0**: PyQt6 모놀리식 데스크톱 앱에서
**React 19 + Tauri 2 + Python 사이드카** 3계층 구조로 전환한 첫 정식 릴리스.

- **프런트엔드**: React 19 + Vite 7 + TypeScript + Tailwind 4, react-virtual 가상 리스트
- **셸**: Tauri 2 (Rust) — 비즈니스 로직 없음, 창/트레이/업데이트/사이드카 생명주기만 담당
- **사이드카**: Python (PyInstaller onedir) — 검색/동기화/인덱스/설정 전 로직, JSON Lines IPC
- **데이터**: legacy와 동일 경로·스키마 공유 → **롤백 시 재인덱싱 불필요**

## 주요 변경 (0.9 대비)

### 신규
- 연관 검색어 칩 (검색 기록 기반 제안, 결과 상단 노출)
- 자동 동기화 + 상태바 카운트다운, 동기화 중 만료 시 busy 지연 수행
- 폴더 단위 선택 동기화 다이얼로그 (계획 미리보기 → 승인 → 진행률)
- 자동 업데이트 (Tauri updater + GitHub Releases, ed25519 서명 검증)
- 3종 테마 (dark / light / warm-dark) 즉시 적용
- 첫 실행 온보딩 다이얼로그 (인덱싱 진행률 포함)
- IPC 장애 시 토스트/상태바 오류 표시 + 자동 복구

### 개선
- 검색: 다중 단어 AND, 포함/정확한 단어만 토글, 폴더 OR 필터(legacy AND 버그 수정),
  발신자 주소 검색, 정렬/기간/첨부 필터, 페이지네이션
- 자동완성: 검색 기록 + 접두사 제안, 드롭다운 클릭 즉시 검색
- 북마크: 사이드바 목록, 클릭 검색, 이름 변경, 재기동 유지
- 설치/제거: NSIS 훅으로 구버전 프로세스 자동 종료, 제거 시 사용자 데이터 보존
- 창 셸: 닫기 = 트레이 상주, 단일 인스턴스 포커스, 트레이 종료 시 좀비 0

### 의도적 동작 변경 (legacy 대비)
- 자동완성 지연 300ms → 200ms
- 폴더 복수 선택: AND(legacy 버그) → OR 합집합
- 미리보기: HTML 렌더 → 정제 평문 (보안/성능)
- 창 닫기: 종료 → 트레이 최소화
- 오류 표시: 모달 → 토스트 + 상태바

## 검증 상태 (샌드박스 자동화)

| 게이트 | 결과 |
|---|---|
| pytest (사이드카/core/IPC T01~T48 + 계약 감사) | 300 passed |
| IPC 런타임 프로브 (43 명령) | PROBE_OK |
| UI 시나리오 자동 (S2~S11, S13~S17, 15종) | 15/15 PASS |
| 런타임 스모크 / 롤백 정합(--full) | OK |
| 계약 정적 감사 (핸들러 ↔ api.ts 전수) | OK |

미검증(Windows 전용): S12(미리보기/열기/내보내기), S18(트레이 동기화),
S19(셸 정책), S20(롤백 드릴) + Rust 컴파일/실 Outlook/서명/업데이트 —
`docs/WINDOWS_VERIFY_RUNBOOK.md` 및 `docs/VM_TEST_CHECKLIST.md`에서 확인 예정.

## 설치 / 업데이트 / 롤백

- 설치: `OutLook.AnyFinder_1.0.0_x64-setup.exe` (NSIS, 시작 메뉴 폴더 생성, currentUser)
- 업데이트: 설정 > 업데이트 탭 또는 기동 시 자동 확인 (GitHub Releases latest.json)
- 롤백: `tools/rollback_to_legacy.ps1` 또는 제어판 제거 후 legacy 재설치 — 데이터 공유, 재인덱스 불필요 (`ROLLBACK.md`)

## 릴리스 산출물 체크리스트 (GitHub Release v1.0.0)

- [ ] `OutLook.AnyFinder_1.0.0_x64-setup.exe`
- [ ] `latest.json` (updater 매니페스트)
- [ ] `OutLook.AnyFinder_1.0.0_x64-setup.exe.sig` (updater 서명 — **3종 전부 필수**)
- [ ] 본 릴리스 노트 본문 첨부

## Known Issues (확정 시 업데이트)

- (Windows 검증 결과 반영 예정)
