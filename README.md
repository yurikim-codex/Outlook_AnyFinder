[README.md](https://github.com/user-attachments/files/28314954/README.md)
# 📧 OutLook AnyFinder for SESUNG Team(Ver0.9)

> **아웃룩 대용량 메일 검색에 업무 시간을 낭비하지 마세요.**
> Outlook 메일의 내용을 로컬 인덱싱하여 초고속 검색하는 Windows 데스크톱 앱 
---

## ✨ 주요 기능

| 기능 | 설명 |
|------|------|
| 🔍 **전문 검색** | 메일 제목, 본문, 발신자, 첨부파일명을 FTS5로 즉시 검색 (< 100ms) |
| 📊 **인덱싱 엔진** | Outlook 메일을 로컬 SQLite DB에 인덱싱 · 진행률 표시 · 일시정지/재개/중단 |
| 💡 **자동완성** | 자주 검색한 단어를 기반으로 검색어 자동완성 |
| ⭐ **검색어 북마크** | 자주 쓰는 검색어를 저장하여 원클릭 재검색 |
| 🔗 **추천 연관 검색어** | 검색 결과 기반으로 연관 키워드를 검색창 하단에 제안 |
| 🎯 **다중 필터** | 폴더, 날짜, 첨부파일, 읽음 상태 등 다양한 조건으로 필터링 |
| 📂 **Outlook 연동** | 검색 결과에서 원본 메일을 Outlook에서 바로 열기 |
| 🔒 **100% 로컬** | 모든 데이터는 사용자 PC에만 저장 · 외부 전송 없음 |

---

## 🖥️ 시스템 요구사항

| 항목 | 요구사항 |
|------|----------|
| **OS** | Windows 10 / 11 |
| **Outlook** | Microsoft Outlook 데스크톱 (설치 & 로그인 필수) |
| **Python** | 3.10+ (개발 시) / 실행 파일(.exe)은 Python 불필요 |
| **디스크** | 500MB 이상 여유 공간 (인덱스 DB용) |
| **메모리** | 4GB 이상 권장 |

---

## 🚀 실행 방법

### 방법 1: .exe 실행 (배포용)
```
OutLookAnyFinder.exe 더블클릭
```
> Python 설치 없이 바로 실행됩니다.

### 방법 2: Python으로 실행 (개발용)
```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 실행
python main.py
```

---

## 📁 프로젝트 구조

```
outlook_anyfinder/
├── main.py                  # 앱 진입점
├── core/                    # 핵심 비즈니스 로직
│   ├── outlook_connector.py # Outlook MAPI 연결
│   ├── mail_extractor.py    # 메일 데이터 정제
│   ├── index_builder.py     # FTS5 인덱스 구축
│   ├── search_engine.py     # 검색 쿼리 실행
│   ├── query_parser.py      # 자연어 → FTS5 변환
│   ├── sync_manager.py      # 증분 동기화
│   ├── autocomplete.py      # 자동완성 엔진
│   ├── bookmark_manager.py  # 검색어 북마크
│   └── related_keywords.py  # 연관 검색어 추천
├── data/                    # 데이터 계층
│   ├── database.py          # SQLite 연결 & 스키마
│   └── models.py            # 데이터 모델
├── ui/                      # UI (PyQt6)
│   ├── main_window.py       # 메인 윈도우
│   ├── search_bar.py        # 검색 바 + 자동완성
│   ├── result_list.py       # 결과 리스트
│   ├── mail_preview.py      # 메일 미리보기
│   └── ...                  # 기타 UI 모듈
├── workers/                 # 백그라운드 스레드
├── utils/                   # 유틸리티
├── tests/                   # 테스트
├── build_exe.py             # .exe 빌드 스크립트
└── requirements.txt         # 의존성
```

---

## 🛠️ 기술 스택

| 영역 | 기술 | 역할 |
|------|------|------|
| 언어 | Python 3.10+ | 전체 개발 |
| GUI | PyQt6 | 데스크톱 UI |
| 메일 접근 | win32com (pywin32) | Outlook MAPI |
| 검색 엔진 | SQLite FTS5 | 전문검색 + BM25 랭킹 |
| HTML 변환 | BeautifulSoup4 | 메일 HTML → 평문 |
| 빌드 | PyInstaller | .exe 패키징 |
| 테스트 | pytest | 단위/통합 테스트 |

---

## 💾 데이터 저장

- **저장 위치**: `~/.outlook_anyfinder/anyfinder.db`
- **형식**: SQLite 단일 파일
- **내용**: 메일 메타데이터 + FTS5 인덱스 + 검색 히스토리 + 북마크
- **원본 메일**: 저장하지 않음 (인덱스만 생성)
- **외부 전송**: 없음 (100% 로컬)

---

## 📋 개발 문서

| 문서 | 설명 |
|------|------|
| [개발상세계획서](./개발상세계획서_OutLook_AnyFinder.md) | 상세 계획, 체크포인트, 테스트 계획 |
| [기술분석서](./기술분석_메일접근_및_인덱싱전략.md) | 메일 접근 방식 & 인덱싱 전략 비교 |

---

## 📜 버전 이력

| 버전 | 날짜 | 내용 |
|------|------|------|
| v0.9 | 2026-05-27 ~ | 최초 개발 (MVP) |

---

> **OutLook AnyFinder** · Made for SESUNG Team [Coding by yurikim]
