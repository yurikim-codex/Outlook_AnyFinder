# 🔍 OutLook AnyFinder — 전체 로직 검토 보고서

> **검토일**: 2026-05-27
> **검토 범위**: 전체 46개 파일 / 8,658줄

---

## 발견된 문제 및 개선 사항

### 🔴 Critical (즉시 수정)

#### 1. 해시맵이 sync_meta에 단일 JSON으로 저장 → 대용량 시 성능 병목

**문제**:
- `_entry_hashes` 키에 `{entry_id: hash}` 전체를 JSON 문자열로 저장
- 메일 10,000건이면 JSON ~500KB, 50,000건이면 ~2.5MB
- 매 동기화마다 전체 JSON을 로드→수정→저장 = O(N) 메모리+I/O
- SQLite의 sync_meta TEXT 컬럼에 수 MB 저장은 비효율

**해결**: 해시맵 전용 테이블(`email_hashes`)로 분리 → 개별 row로 관리

#### 2. `_do_smart_sync`에서 설정의 자동/수동 모드가 반영 안 됨

**문제**:
- 설정에 `sync.auto_sync`와 `sync.interval_minutes` 존재
- `main_window._setup_auto_sync()`에서 타이머는 설정하지만
- 설정 변경 후 타이머를 재시작하는 로직 없음
- "수동만" 선택 시 interval=0 → 타이머가 0ms마다 실행되는 버그

**해결**: 설정 변경 시 타이머 재설정, interval=0이면 타이머 비활성화

#### 3. settings_dialog 저장 후 main_window에 반영 안 됨

**문제**:
- `settings_saved` 시그널은 emit하지만 main_window에서 받아서 처리하는 로직 없음
- 설정 변경 (자동 동기화 끄기 등)이 앱 재시작 전까지 적용 안 됨

**해결**: main_window에서 settings_saved 시그널 연결 → 타이머 재설정

---

### 🟡 Important (품질 향상)

#### 4. IndexBuilder와 SyncManager에 해시 로직 중복

**문제**: `_load_hashes`, `_save_hashes`, `HASH_META_KEY`가 양쪽에 중복

**해결**: 해시 테이블로 통합하면 자동 해결

#### 5. 동기화 모드 선택 UI 없음 (사용자 요구사항)

**문제**: 사용자가 "자동 업데이트" vs "수동 업데이트"를 직관적으로 선택할 수 있는 UI가 설정 화면에만 있고, 사이드바에서 바로 전환 불가

**해결**: 사이드바 동기화 카드에 "자동/수동" 토글 추가

#### 6. SyncWorker가 SyncManager를 사용하지 않음

**문제**: `workers/sync_worker.py`는 구형 `IndexBuilder` 기반, 스마트 동기화(SyncManager) 미사용

**해결**: SyncWorker를 SyncManager 기반으로 재작성

---

### 🟢 Minor (개선 권장)

#### 7. FTS5 optimize를 매 동기화마다 실행 → 불필요한 오버헤드

#### 8. 검색 히스토리에 중복 연관 기록 가능 (세션 로그 무한 증가)

---
