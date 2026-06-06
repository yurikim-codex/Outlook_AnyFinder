# 🔍 OutLook AnyFinder — 전체 로직 검토 보고서

> **검토 갱신일**: 2026-06-04  
> **대상 버전**: Ver0.9, 사내 배포 준비 버전  
> **검토 범위**: Outlook 연동, 동기화, 검색, UI, 설정, 배포 패키징 전반

---

## 1. 검토 요약

기존 검토 보고서에서 지적했던 주요 문제들은 대부분 개선되었습니다.

특히 아래 항목은 현재 코드에 반영되어 있습니다.

| 구분 | 기존 이슈 | 현재 상태 |
|---|---|---|
| 해시 저장 구조 | `sync_meta` 단일 JSON 저장으로 대용량 병목 | `email_hashes` 테이블 기반으로 개선됨 |
| 동기화 UI 멈춤 | Outlook 스캔/비교가 메인 스레드에서 실행 | `SyncPlanWorker`, `SyncExecuteWorker`로 분리됨 |
| 설정 반영 | 설정 저장 후 즉시 반영 불안정 | `settings_saved` 연결 및 테마/동기화 설정 반영 구조 추가 |
| 자동 동기화 | 설정 저장 후 동작 불안정 | 자동 동기화 타이머 및 남은 시간 표시 추가 |
| 중복 동기화 | 자동/수동 동기화가 겹쳐 DB lock 가능 | 동기화 중 실행 차단 및 자동 동기화 연기 로직 추가 |
| 검색 UI | 연관검색어/자동완성 팝업 등 UI 혼선 | 검색 UI 단순화, 메일주소 인라인 자동완성만 유지 |
| 배포 | 개발 실행 중심 | PyInstaller spec, release script, release docs 추가 |

---

## 2. 현재 주요 아키텍처

### 2.1 앱 진입점

```text
main.py
└─ AppController
   ├─ QApplication 초기화
   ├─ DB 초기화
   ├─ 검색 기록 초기화
   ├─ 테마 적용
   ├─ 최초 인덱싱/메인 윈도우 생성
   ├─ 수동 동기화 플로우 관리
   ├─ 백그라운드 동기화/중지 관리
   └─ 트레이 아이콘 관리
```

---

### 2.2 동기화 구조

현재 동기화는 크게 두 단계로 분리되어 있습니다.

```text
1. SyncPlanWorker
   └─ Outlook 스캔 + DB 비교 + 동기화 계획 생성

2. SyncExecuteWorker
   └─ 승인된 계획에 따라 DB 반영
```

자동 동기화는 `SyncWorker`를 통해 증분 방식으로 실행됩니다.

```text
자동 동기화
→ last_sync_time 이후 변경/추가 메일만 스캔
→ 삭제 감지는 하지 않음
```

수동 동기화도 최초 동기화 이후에는 증분 스캔을 사용하도록 변경되었습니다.

---

### 2.3 검색 구조

```text
SearchBar
→ MainWindow._execute_search()
→ SearchEngine.search()
→ query_parser.parse_query()
→ SQLite FTS5 / LIKE 조건 검색
```

현재 검색 정책:

```text
기본: 포함 검색
정확한 단어만 체크: FTS5 정확 단어 검색
+ 검색: AND 멀티 검색
메일주소 검색: LIKE 기반 검색
```

---

### 2.4 UI 구조

```text
MainWindow
├─ Sidebar
├─ SearchBar
├─ FilterBar
├─ ResultList
│  └─ MailCard
└─ MailPreview
```

UI 테마:

```text
dark  : 모던 다크 / Slack + Outlook 스타일
light : Mac OS / Linear 스타일 화이트 테마
```

---

## 3. 해결된 주요 이슈

### 3.1 해시 저장 구조 개선

#### 기존 문제

과거에는 메일 해시맵을 `sync_meta`에 JSON 문자열로 저장하는 구조였습니다.

문제점:

```text
메일 수 증가 시 JSON 크기 증가
동기화 때마다 전체 JSON 로드/저장
O(N) I/O 및 메모리 병목
```

#### 현재 개선

현재는 `email_hashes` 테이블을 사용합니다.

```sql
CREATE TABLE IF NOT EXISTS email_hashes (
    entry_id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL
);
```

장점:

```text
entry_id 단위 조회/갱신 가능
대용량 메일에서도 효율적
동기화 비교 성능 개선
```

상태: **해결됨**

---

### 3.2 메인 스레드 동기화 병목 개선

#### 기존 문제

Outlook 전체 스캔/비교가 메인 UI 스레드에서 실행되어 앱이 멈추는 현상이 있었습니다.

#### 현재 개선

아래 워커로 분리되었습니다.

```text
workers/sync_plan_worker.py
workers/sync_execute_worker.py
```

효과:

```text
Outlook 스캔 중 UI 반응 유지
동기화 중 검색 가능
진행률 실시간 표시
동기화 중지 가능
```

상태: **해결됨**

---

### 3.3 자동 동기화 복구 및 중복 실행 방지

#### 기존 문제

자동 동기화가 설정과 맞지 않거나, 수동 동기화와 겹치면 `database is locked` 오류가 발생할 수 있었습니다.

#### 현재 개선

현재 자동 동기화는 다음을 지원합니다.

```text
설정 저장 반영
다음 자동동기화까지 남은 시간 표시
동기화 중이면 자동 동기화 1분 연기
증분 스캔 사용
```

표시 예:

```text
자동동기화 09분58초
```

상태: **개선됨**

주의:

```text
Outlook COM 호출 자체가 오래 걸리는 경우, 중지/연기 반응이 즉시 보이지 않을 수 있음
```

---

### 3.4 검색 기능 개선

반영된 기능:

```text
기본 포함 검색
정확한 단어만 옵션
+ 멀티 검색
메일 주소 검색
메일 주소 인라인 자동완성
첨부파일명 검색
서명/본문 삽입 이미지 첨부 제외
```

검색 예:

```text
주관
바이오+견적서
kim@company.com
subject:견적서
첨부파일:계약서
```

상태: **개선됨**

---

### 3.5 검색 리스트 및 상세 UI 개선

반영된 기능:

```text
검색 결과 카드형 UI
둥근 테두리
선택 상태 명확화
가로 폭에 따른 말줄임
높이 고정
첨부파일 clip 표시
페이지네이션
맨처음/마지막 이동
답장/전달 버튼 제거
Outlook에서 열기 유지
```

상태: **개선됨**

---

### 3.6 설정 및 테마 개선

반영된 기능:

```text
설정 창 크기 확장
UI 테마 탭 추가
모던 다크 테마
Mac OS / Linear 스타일 화이트 테마
저장 후 테마 반영
데이터 초기화 확인창 버튼 스타일 개선
```

상태: **개선됨**

---

### 3.7 배포 패키징 추가

추가된 배포 관련 파일:

```text
OutLookAnyFinder.spec
version_info.txt
build_release.ps1
build_release.bat
build_exe.py
release_docs/
.gitignore
```

지원 빌드:

```text
onedir 권장 배포
onefile 선택 배포
release zip 자동 생성
```

상태: **완료됨**

---

## 4. 현재 남아있는 주의사항 및 개선 권장 사항

### 🟡 4.1 Outlook COM 중지 즉시성 한계

동기화 중지 버튼이 추가되었지만, Outlook COM이 특정 메일/폴더 접근 호출을 수행 중이면 Python 코드에서 즉시 중단할 수 없습니다.

현재 구조:

```text
COM 호출 반환
→ should_stop 확인
→ 중단
```

권장 개선:

```text
폴더 단위/메일 배치 단위 timeout 정책 추가 검토
장시간 응답 없는 폴더 skip 옵션 추가 검토
```

우선순위: **중간**

---

### 🟡 4.2 자동 증분 동기화의 삭제 감지 제한

자동/증분 동기화는 `LastModificationTime > last_sync_time` 기준으로 변경/추가분만 스캔합니다.

장점:

```text
매번 전체 스캔하지 않음
빠름
```

제한:

```text
삭제된 메일 감지는 전체 목록 비교가 필요하므로 자동 증분 동기화에서는 정확히 처리하기 어려움
```

현재 정책:

```text
증분 동기화: 추가/수정 중심
전체/정밀 동기화: 삭제 감지 가능
```

권장 개선:

```text
설정 또는 동기화 창에 '정밀 동기화/전체 재스캔' 버튼 추가
주 1회 정밀 동기화 옵션 추가
```

우선순위: **중간**

---

### 🟡 4.3 DB 마이그레이션 체계 필요

현재 기능이 빠르게 추가되면서 DB 스키마가 확장되었습니다.

현재는 `CREATE TABLE IF NOT EXISTS` 중심 구조입니다.

권장:

```text
schema_version 메타 도입
버전별 마이그레이션 함수 추가
```

예:

```text
sync_meta.schema_version = 2
migrate_v1_to_v2()
```

우선순위: **중간**

---

### 🟢 4.4 설정 UI에서 제거된 기능 정리

검색어 자동완성/연관검색어 기능은 제거되었지만, 일부 설정 UI에는 과거 자동완성 관련 항목이 남아 있을 수 있습니다.

예:

```text
검색 탭의 자동완성 최대 표시 수
```

현재 동작에는 큰 문제는 없으나 UI 정합성을 위해 제거하거나 의미를 변경하는 것을 권장합니다.

우선순위: **낮음**

---

### 🟢 4.5 테스트 보강 권장

현재 전체 테스트는 통과합니다.

```text
198 passed
```

추가하면 좋은 테스트:

```text
검색단어포함 LIKE 검색 테스트
정확한 단어만 FTS 검색 테스트
+ 멀티 검색 테스트
메일 주소 검색 테스트
폴더별 동기화 비교 범위 테스트
증분 동기화 삭제 미감지 정책 테스트
데이터 초기화 후 폴더 카운트 0 확인 테스트
```

우선순위: **낮음~중간**

---

## 5. 최신 주요 파일 변경 현황

### 동기화 관련

```text
core/sync_manager.py
core/outlook_connector.py
workers/sync_plan_worker.py
workers/sync_execute_worker.py
workers/sync_worker.py
workers/indexing_worker.py
main.py
```

### 검색 관련

```text
core/query_parser.py
core/search_engine.py
ui/search_bar.py
ui/result_list.py
ui/mail_card.py
ui/mail_preview.py
```

### UI/설정 관련

```text
ui/main_window.py
ui/sidebar.py
ui/filter_bar.py
ui/settings_dialog.py
ui/sync_folder_dialog.py
ui/theme.py
ui/indexing_dialog.py
```

### 데이터/배포 관련

```text
data/database.py
OutLookAnyFinder.spec
version_info.txt
build_release.ps1
build_release.bat
build_exe.py
release_docs/
.gitignore
README.md
실행_가이드.md
```

---

## 6. 최종 평가

현재 버전은 초기 MVP 대비 다음 부분이 크게 개선되었습니다.

```text
동기화 안정성
UI 반응성
증분 동기화 성능
검색 UX
메일 주소 검색
카드형 검색 리스트
테마 지원
사내 배포 준비도
```

현재 상태는 **사내 파일럿 배포가 가능한 수준**으로 판단됩니다.

다만 실제 Outlook/Exchange 환경은 사용자별 메일함 크기, 공유 메일함, 보안 정책, COM 응답 속도에 따라 차이가 있으므로, 사내 배포 전 아래 테스트를 권장합니다.

```text
1. 메일 1천 건 이하 사용자
2. 메일 1만 건 이상 사용자
3. 하위 폴더 많은 사용자
4. 첨부파일 많은 사용자
5. 보낸편지함 중심 사용자
6. 받은편지함 중심 사용자
7. 자동 동기화 ON 사용자
8. 데이터 초기화 후 재동기화 사용자
```

---

## 7. 권장 다음 작업

| 우선순위 | 작업 | 이유 |
|---|---|---|
| 높음 | 사내 테스트 PC에서 exe 빌드/실행 검증 | PyInstaller + Outlook COM은 실제 Windows 환경 검증 필수 |
| 높음 | 데이터 초기화 후 재동기화 테스트 | 폴더 카운트/검색 리스트 갱신 확인 필요 |
| 중간 | 정밀 동기화 버튼 추가 | 증분 동기화의 삭제 감지 제한 보완 |
| 중간 | DB schema_version 도입 | 향후 업데이트 안정성 확보 |
| 중간 | 설정 검색 탭 정리 | 제거된 자동완성 옵션 UI 정합성 개선 |
| 낮음 | 코드 서명 검토 | SmartScreen/백신 경고 감소 |

---

> 본 보고서는 현재까지 반영된 수정사항 기준으로 갱신되었습니다.

---

## 8. 추가 검토 갱신 — 기간 동기화/Outlook COM/배포 안정화

### 8.1 기간 동기화 기준 재점검

최근 필드 테스트에서 `3개월`, `6개월`, `1년`, `전체` 범위 선택 시 실제 기대 범위와 다른 카운트/동기화 대상이 잡힐 수 있는 문제가 확인되었습니다.

보완 내용:

```text
기간 동기화: ReceivedTime/SentOn 기준
증분 동기화: LastModificationTime 기준
Restrict 실패 시 전체 Count를 반환하지 않고 직접 날짜 판정으로 카운트
기존 인덱싱 범위보다 넓은 범위를 요청하면 증분이 아니라 기간 스캔 수행
```

관련 파일:

```text
core/outlook_connector.py
core/sync_manager.py
main.py
workers/indexing_worker.py
workers/sync_plan_worker.py
workers/sync_execute_worker.py
workers/sync_worker.py
```

### 8.2 범위 커버리지 메타

현재 DB가 어느 기간까지 커버하는지 아래 메타로 관리합니다.

```text
sync_meta.indexed_range_months
```

값 의미:

```text
3  = 최근 3개월
6  = 최근 6개월
12 = 최근 1년
0  = 전체
-1 = 메타 없음
```

### 8.3 Outlook COM 배포 진단

배포본에서 Outlook 동기화가 Mock처럼 보이거나 실패하는 것을 방지하기 위해 Windows에서는 pywin32/win32com import 실패 시 명시적으로 오류를 발생시키도록 변경되었습니다.

추가 진단 파일:

```text
outlook_com_check.py
```

진단 명령:

```powershell
py -3 outlook_com_check.py
```

### 8.4 필드 테스트 빌드 스크립트

필드 테스트용 빌드를 쉽게 하기 위해 아래 스크립트를 추가했습니다.

```text
field_test_build.bat
필드테스트_빌드.bat
필드테스트_빌드_가이드.md
```

배치 파일은 Windows CMD 인코딩 문제를 피하기 위해 영문 메시지 중심으로 구성했습니다.
