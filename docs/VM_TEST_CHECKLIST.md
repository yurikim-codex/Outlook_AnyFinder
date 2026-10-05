# 클린 VM 설치 테스트 체크리스트 (Phase 5-7)

> 대상 VM: Windows 10 22H2 / Windows 11 (각 1기) × Outlook 2016 / Microsoft 365 Apps (각 1세트).
> 준비: 신규 생성 VM (Office/WebView2 외 사전 설치 없음), 설치본 `*-setup.exe` + `sesung-codesign.cer`.
> 모든 항목 ✅ 여야 릴리스 승인. 실패 항목은 이슈 등록 후 재배포.

## A. 설치

- [ ] A1 설치본 실행 → 언어 선택창(Korean/English) 노출, Korean 기본
- [ ] A2 currentUser 모드 — 관리자 권한 승격(UAC) 없음
- [ ] A3 시작 메뉴 폴더 "OutLook AnyFinder" 생성, 바탕화면 아이콘 옵션 동작
- [ ] A4 WebView2 오프라인 설치자 자동 진행 (망 분리 VM에서도 완료)
- [ ] A5 설치 중 구버전 실행 중이면 hooks가 자동 종료 (파일 잠금 오류 0)
- [ ] A6 설치 완료 → 첫 실행까지 10초 이내 (WebView2 기설치 기준)

## B. 첫 실행·온보딩

- [ ] B1 창 표시 ≤ 1초, "사이드카 기동 중" 배너 후 자동 활성화
- [ ] B2 작업관리자: `OutlookAnyFinderSidecar.exe` 1건만 (중복 spawn 없음)
- [ ] B3 첫 실행 다이얼로그 → 인덱싱 진행률 → 완료 토스트
- [ ] B4 Outlook 미설동/미설치 시 에러 토스트 + 재시도 안내 (크래시 없음)
- [ ] B5 사이드카 콘솔 창 없음 (CREATE_NO_window 검증)

## C. 핵심 기능

- [ ] C1 검색: 키워드/다중단어/메일주소/정확한 단어만 — 결과·스니펫 정상
- [ ] C2 필터: 폴더 OR/첨부/기간/정렬 조합
- [ ] C3 미리보기 본문 · Outlook에서 열기 · 내보내기(.msg)
- [ ] C4 폴더 동기화: plan 수치 ↔ 실제 변경 일치, 진행률, 취소
- [ ] C5 동기화 중 검색 응답 (COM 블로킹 없음)
- [ ] C6 자동 동기화: 간격 도래 시 수행, busy면 지연 후 수행
- [ ] C7 북마크/검색기록/설정 유지 (재기동 후)
- [ ] C8 테마 3종 전환 즉시 반영, 재기동 유지

## D. 장애·회복

- [ ] D1 사이드카 taskkill → 15초 내 자동 재시작 + UI 복구
- [ ] D2 앱 강제 종료 후 재실행 — 잔존 프로세스 자동 정리(단일 인스턴스)
- [ ] D3 Outlook 종료 상태 검색 → DB 기반 결과 계속 동작
- [ ] D4 설정>업데이트 확인 → "최신 버전" 또는 새 버전 설치 흐름

## E. 종료·제거·데이터

- [ ] E1 창 닫기 → 트레이 숨김 (프로세스 유지), 트레이 종료 시 사이드카 포함 전부 종료
- [ ] E2 종료 후 작업관리자 좀비 0건 (`OutlookAnyFinderSidecar.exe` 없음)
- [ ] E3 제거(uninstall) → 프로그램 삭제, **데이터(~\.outlook_anyfinder) 보존**
- [ ] E4 재설치 → 재색인 없이 즉시 검색 (기존 DB 재사용)
- [ ] E5 롤백 드릴: `tools\rollback_to_legacy.ps1` → legacy 동작 → 신버전 복귀 (S20)

## F. 보안·백신

- [ ] F1 Windows Defender 전체 검사 — 오탐 0
- [ ] F2 V3(사내 표준) 수동 검사 — 오탐 0
- [ ] F3 서명 확인: 속성→디지털 서명 목록에 SESUNG 인증서, 타임스탬프 유효
- [ ] F4 SmartScreen: cer 배포 PC에서 경고 없음 (미배포 PC 경고 = 예상 동작 기록)

## G. 로그·진단

- [ ] G1 `%LOCALAPPDATA%\com.sesung.outlook-anyfinder\logs\desktop.log` 기록 확인
- [ ] G2 `~\.outlook_anyfinder\logs\sidecar.log` 로테이션 동작 (2MB×3)
- [ ] G3 문제 재현 시 두 로그 쌍으로 원인 특정 가능 (스크린샷 첨부)

## 기록

| VM | OS | Outlook | 수행일 | 수행자 | 결과 | 비고 |
|---|---|---|---|---|---|---|
| | | | | | | |
