# 📧 OutLook AnyFinder for SESUNG Team (Ver0.9.1)

> **Outlook 대용량 메일 검색에 쓰는 시간을 줄이기 위한 로컬 메일 검색 도구입니다.**  
> Microsoft Outlook 데스크톱 메일을 사용자 PC에 로컬 인덱싱하고, SQLite FTS5 기반으로 빠르게 검색합니다.

---

## ✨ 주요 기능

| 기능 | 설명 |
|---|---|
| 🔍 **고속 메일 검색** | 제목, 본문, 발신자, 수신자, CC, 첨부파일명을 로컬 DB에서 빠르게 검색 |
| 🔎 **포함 검색 / 정확 단어 검색** | 기본은 검색어 포함 검색이며, `정확한 단어만` 옵션으로 FTS 단어 검색 가능 |
| ➕ **멀티 조건 검색** | `바이오+견적서`처럼 `+`로 여러 단어를 AND 조건 검색 |
| 📧 **메일 주소 검색** | `kim@company.com` 같은 메일 주소 검색 및 인라인 자동완성 지원 |
| 📎 **첨부파일 검색/표시** | 첨부파일명 검색, 첨부 확장자 필터, 검색 리스트 내 clip 표시 |
| 🖼 **서명 이미지 제외** | 서명/본문 삽입 이미지로 판단되는 파일은 첨부파일 리스트에서 제외 |
| 📊 **로컬 인덱싱** | Outlook 메일을 SQLite DB에 로컬 인덱싱, 진행률/일시정지/중단/백그라운드 지원 |
| 🔄 **증분 동기화** | 최초 동기화 이후에는 변경/추가된 메일만 빠르게 스캔 및 동기화 |
| ⏱ **자동 동기화** | 설정한 주기로 자동 동기화, 다음 동기화까지 남은 시간 표시 |
| ⏹ **동기화 중지** | 동기화 중 사이드바에서 중지 가능 |
| 📈 **스캔/동기화 진행률** | 선택 폴더 스캔 진행률과 동기화 진행률을 사이드바에 표시 |
| ⭐ **검색어 북마크** | 자주 쓰는 검색어와 필터 상태를 저장하여 재검색 가능 |
| 🎯 **필터** | 전체/받은편지함/보낸편지함, 날짜, 첨부 여부/확장자, 정렬 지원 |
| 📄 **페이지네이션** | 검색 결과가 많을 때 맨처음/이전/다음/마지막 페이지 이동 지원 |
| 📂 **Outlook 연동** | 검색 결과에서 원본 메일을 Outlook에서 바로 열기 |
| 🎨 **UI 테마** | 모던 다크 테마와 Mac OS / Linear 스타일 화이트 테마 지원 |
| 🔒 **100% 로컬** | 메일 인덱스와 설정은 사용자 PC에만 저장, 외부 전송 없음 |

---

## 🖥️ 시스템 요구사항

| 항목 | 요구사항 |
|---|---|
| **OS** | Windows 10 / 11 |
| **Outlook** | Microsoft Outlook 데스크톱 앱 설치 및 로그인 완료 |
| **Python** | 사용자 실행 시 불필요, 개발/빌드 시 Python 3.10+ 권장 |
| **디스크** | 500MB 이상 여유 공간 권장 |
| **메모리** | 4GB 이상 권장 |

> Outlook이 없는 Windows 외 환경에서는 Mock 데이터 기반 데모 모드로 동작할 수 있습니다.

---

## 🚀 실행 방법

### 방법 1. 사내 배포용 `.exe` 실행

배포 ZIP 압축 해제 후 아래 파일을 실행합니다.

```text
OutLookAnyFinder/OutLookAnyFinder.exe
```

> Python 설치 없이 실행 가능합니다.  
> Windows 보안 경고가 나오면 사내 배포 파일인지 확인 후 `추가 정보 → 실행`을 선택하세요.

자세한 내용은 다음 문서를 참고하세요.

```text
실행_가이드.md
release_docs/실행_가이드.txt
release_docs/문제해결_가이드.txt
```

---

### 방법 2. Python으로 개발 실행

```bash
pip install -r requirements.txt
python main.py
```

---

## 📦 사내 배포 패키지 빌드

기본 권장 방식은 PyInstaller `onedir` 방식입니다.

```powershell
cd C:\Arena\Outlook_AnyFinder
.\build_release.bat
```

또는:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_release.ps1
```

빌드 결과:

```text
release/OutLookAnyFinder_v0.9.1_YYYYMMDD_HHMM.zip
```

단일 exe가 필요한 경우:

```powershell
.\build_release.bat -OneFile
```

또는:

```powershell
python build_exe.py --onefile
```

배포 관련 파일:

```text
OutLookAnyFinder.spec
version_info.txt
build_release.ps1
build_release.bat
build_exe.py
release_docs/
```

---

## 🔍 검색 사용 예시

| 입력 | 동작 |
|---|---|
| `견적서` | 견적서가 포함된 메일 검색 |
| `주관` | 기본 포함 검색: 주관, 주관기관, 사업주관 등 검색 |
| `정확한 단어만` 체크 + `주관` | 정확한 단어 기준 검색 |
| `바이오+견적서` | 바이오와 견적서가 모두 포함된 메일 검색 |
| `kim@company.com` | 메일 주소 검색 |
| `subject:견적서` | 제목에서 견적서 검색 |
| `첨부파일:계약서` | 첨부파일명에서 계약서 검색 |
| `첨부:xlsx` | xlsx 첨부파일 필터 검색 |
| `폴더:받은편지함` | 받은편지함 메일 검색 |
| `날짜:2026-05` | 2026년 5월 메일 검색 |

---

## 🔄 동기화 방식

### 최초 동기화

사용자가 선택한 폴더와 범위 기준으로 Outlook 메일을 인덱싱합니다.

선택 가능:

```text
받은편지함
보낸편지함
임시보관함
지운편지함
하위 폴더 포함 여부
3개월 / 6개월 / 1년 / 전체
```

### 이후 동기화

이전 동기화 이후 변경되거나 추가된 메일만 스캔합니다.

```text
LastModificationTime > last_sync_time
```

즉, 기존 데이터와 동일한 메일은 처음부터 다시 스캔하지 않습니다.

### 자동 동기화

설정한 주기에 따라 자동으로 증분 동기화를 수행합니다.

```text
자동동기화 09분58초
```

처럼 다음 동기화까지 남은 시간이 표시됩니다.

---

## 🎨 UI 테마

설정 → `UI 테마` 탭에서 선택할 수 있습니다.

| 테마 | 설명 |
|---|---|
| 모던 다크 테마 | Slack/Outlook 느낌의 다크 사이드바와 카드형 검색 리스트 |
| 화이트 테마 | Mac OS / Linear 스타일의 밝은 UI, 부드러운 색상 계층, 명확한 선택 상태 |

---

## 📁 프로젝트 구조

```text
Outlook_AnyFinder/
├── main.py                         # 앱 진입점 / AppController
├── core/                           # 핵심 비즈니스 로직
│   ├── outlook_connector.py        # Outlook COM/MAPI 연결 및 메일 추출
│   ├── mail_extractor.py           # raw 메일 데이터 → EmailRecord 변환
│   ├── index_builder.py            # 전체 인덱싱/FTS 구축
│   ├── search_engine.py            # 검색 쿼리 실행
│   ├── query_parser.py             # 검색어 파싱 및 FTS/LIKE 조건 생성
│   └── sync_manager.py             # 증분 동기화 계획/실행
├── data/
│   ├── database.py                 # SQLite 연결, 스키마, 메타 정보
│   └── models.py                   # 데이터 모델
├── ui/
│   ├── main_window.py              # 메인 윈도우
│   ├── sidebar.py                  # 사이드바/동기화 진행 표시
│   ├── search_bar.py               # 검색창/정확 단어 옵션/메일주소 인라인 완성
│   ├── filter_bar.py               # 필터 바
│   ├── result_list.py              # 검색 결과 리스트/페이지네이션
│   ├── mail_card.py                # 검색 결과 카드
│   ├── mail_preview.py             # 메일 상세 미리보기
│   ├── settings_dialog.py          # 설정 화면
│   ├── sync_folder_dialog.py       # 동기화 대상 폴더/범위 선택
│   └── theme.py                    # 다크/화이트 테마 토큰
├── workers/
│   ├── indexing_worker.py          # 최초/전체 인덱싱 QThread
│   ├── sync_plan_worker.py         # 동기화 스캔/비교 QThread
│   ├── sync_execute_worker.py      # 승인된 동기화 실행 QThread
│   └── sync_worker.py              # 자동 증분 동기화 QThread
├── utils/                          # 설정, 날짜, HTML 정리 유틸
├── tests/                          # 테스트
├── release_docs/                   # 사내 배포 문서
├── build_exe.py                    # Python 빌드 스크립트
├── build_release.ps1               # 사내 배포 패키지 빌드 스크립트
├── build_release.bat               # Windows용 빌드 실행 배치
├── OutLookAnyFinder.spec           # PyInstaller onedir spec
├── version_info.txt                # Windows exe 메타데이터
├── 실행_가이드.md                  # 설치/실행 가이드
├── .gitignore
└── requirements.txt
```

---

## 🛠️ 기술 스택

| 영역 | 기술 | 역할 |
|---|---|---|
| 언어 | Python 3.10+ | 전체 개발 |
| GUI | PyQt6 | Windows 데스크톱 UI |
| 메일 접근 | pywin32 / win32com | Outlook COM/MAPI 접근 |
| 검색 엔진 | SQLite FTS5 + LIKE | 전문 검색 및 포함 검색 |
| DB | SQLite WAL | 로컬 인덱스 저장 |
| HTML 정리 | BeautifulSoup4 | HTML 메일 본문 정리 |
| 빌드 | PyInstaller | exe 패키징 |
| 테스트 | pytest | 단위/통합 테스트 |

---

## 💾 데이터 저장 위치

사용자별 로컬 경로에 저장됩니다.

```text
C:\Users\사용자명\.outlook_anyfinder\
```

주요 파일:

```text
anyfinder.db
config.json
```

저장 내용:

```text
메일 인덱스
FTS5 검색 인덱스
동기화 메타 정보
북마크
설정
```

외부 서버로 전송하지 않습니다.

---

## 📋 문서

| 문서 | 설명 |
|---|---|
| [실행_가이드.md](./실행_가이드.md) | 설치/실행/검색/동기화/배포 가이드 |
| [OPTIMIZATION_REPORT.md](./OPTIMIZATION_REPORT.md) | 최적화 보완 보고서 (v0.9.1) |
| [REVIEW_REPORT.md](./REVIEW_REPORT.md) | 전체 로직 검토 보고서 |
| [release_docs/README_사내배포.txt](./release_docs/README_사내배포.txt) | 사내 배포 패키지 README |
| [release_docs/실행_가이드.txt](./release_docs/실행_가이드.txt) | 사용자용 실행 안내 |
| [release_docs/문제해결_가이드.txt](./release_docs/문제해결_가이드.txt) | 문제 해결 안내 |
| [release_docs/배포담당자_체크리스트.txt](./release_docs/배포담당자_체크리스트.txt) | 배포 담당자 체크리스트 |

---

## 📜 버전 이력

| 버전 | 내용 |
|---|---|
| v0.9.1 | 재동기화 누락·합계 불일치·삭제감지 보완, 사이드바 개선, 설정 UX 강화 (2026-06-07) |
| v0.9 | Outlook 로컬 인덱싱/검색 MVP, 증분 동기화, 자동 동기화, 테마, 사내 배포 패키지 지원 |

---

## GitHub 업로드 시 주의

`.gitignore`에 의해 아래 항목은 제외됩니다.

```text
build/
dist/
release/
*.exe
*.zip
*.db
__pycache__/
```

GitHub에는 소스, 테스트, 빌드 스크립트, 배포 문서만 업로드하는 것을 권장합니다.

---

> **OutLook AnyFinder** · Made for SESUNG Team [Coding by yurikim]

---

## 🔎 최근 동기화/배포 보완 사항

### 기간 동기화 기준 보정

동기화 범위 `3개월 / 6개월 / 1년 / 전체`는 메일의 실제 날짜 기준으로 처리합니다.

```text
받은편지함 계열: ReceivedTime 기준
보낸편지함 계열: SentOn 기준
증분 동기화: LastModificationTime 기준
```

또한 기존에 `3개월`로 인덱싱한 뒤 `6개월`, `1년`, `전체`처럼 더 넓은 범위를 선택하면 증분 동기화가 아니라 요청한 기간 기준으로 다시 스캔합니다. 이 범위 커버리지는 `sync_meta.indexed_range_months`에 기록됩니다.

### Outlook COM 진단

배포본에서 Outlook 동기화가 되지 않는 경우, 빌드/테스트 PC에서 아래 진단 스크립트를 실행할 수 있습니다.

```powershell
py -3 outlook_com_check.py
```

정상 예:

```text
OK: pywin32 modules imported
OK: Outlook COM connected
```

> 이 앱은 Classic Outlook 데스크톱 앱의 COM 연동을 사용합니다. 새 Outlook(New Outlook, 웹 기반)은 COM 연동이 제한될 수 있습니다.

### 필드 테스트 빌드

필드 테스트용 배포 패키지는 아래 스크립트로 생성합니다.

```powershell
.\field_test_build.bat
```

한글 파일명을 선호하는 경우:

```powershell
.\필드테스트_빌드.bat
```

빌드 결과 ZIP은 `release/` 폴더에 생성됩니다.
