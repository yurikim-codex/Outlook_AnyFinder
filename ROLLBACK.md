# 롤백 절차 — React+Tauri 판 → legacy PyQt6 판 (Phase 4-6)

## 왜 데이터 없이 롤백되는가

| 공유 자산 | 경로 | 비고 |
|---|---|---|
| 메일 인덱스 DB | `~/.outlook_anyfinder/anyfinder.db` | 신구 동일 경로·동일 스키마(`schema_version=1`). 신버전은 재색인 없이 열린다(테스트 test_20) |
| 설정 | `~/.outlook_anyfinder/config.json` | **단일 스키마** — 신UI는 레거시 키 이름을 그대로 사용(test_19). 추가 키는 레거시가 무시 |
| 북마크/검색기록 | 동일 DB 내 테이블 | 양방향 공유 |
| 로그 | `~/.outlook_anyfinder/logs/` | 신구 각자 파일(sidecar.log / desktop.log) |

→ 롤백은 **실행 파일 교체만** 필요. 데이터 마이그레이션/백업 복원 불요.

## 롤백 결정 기준

- 치명 결함으로 검색/동기화 불가 + 즉시 업무 복귀 필요 시
- `tools/rollback_check.py`가 1(문제)을 반환하고 복구가 안 될 시 (데이터는 안전 — 구버전으로 계속 사용 가능)

## 절차 (Windows)

```powershell
# 한 방 스크립트 (프로세스 중지 → 무결성 검사 → legacy 빌드 → 기동 → 재검사)
powershell -File tools\rollback_to_legacy.ps1          # 빌드 포함
powershell -File tools\rollback_to_legacy.ps1 -SkipBuild  # 기존 dist 빌드 재사용(더 빠름)
```

수동 단계 (스크립트 불가 시):
1. 신버전 종료: 트레이 → 종료, 작업관리자에서 `OutlookAnyFinderSidecar.exe` 잔존 확인 후 종료
2. `python tools\rollback_check.py` → 0 확인
3. `python build_exe.py` (또는 기존 `dist\OutLookAnyFinder\OutLookAnyFinder.exe` 재사용)
4. legacy 실행 → 로그인-less 즉시 사용 (인덱스 그대로)
5. 신버전 복귀도 동일: Tauri 설치본 실행即可 — 데이터 공유라 재색인 없음

## 주의

- **warm-dark 테마** 선택 상태로 롤백하면 legacy는 `apply_theme` 폴백으로 dark 표시 (크래시 없음, test 커버)
- 신UI 전용 설정 키(`search.contains_search`)는 legacy가 무시 — 동작 기본값(포함 검색)과 동일
- NSIS 설치본 제거(uninstaller)는 데이터 디렉터리를 지우지 않음 — 제거 후 legacy 사용 가능
- 롤백 후 새 버전 재설치 시 사이드카가 기존 DB를 그대로 mở (test_20 회귀 테스트로 고정)

## 검증 상태

- `tools/rollback_check.py` — 샌드박스 실실행 ✅ (mock DB 대상 --full 포함)
- `tools/rollback_to_legacy.ps1` — Windows 실기기 검증 대기 (S20)
- 데이터 공유 전제 회귀 테스트: test_19(config 단일 스키마), test_20(재색인 없음)
