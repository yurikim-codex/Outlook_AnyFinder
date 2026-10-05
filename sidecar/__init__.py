"""
OutLook AnyFinder Python Sidecar — IPC 비즈니스 로직 프로세스.

Tauri(Rust) 셸이 이 패키지를 자식 프로세스로 spawn 하고,
stdin/stdout JSON Lines 프로토콜로 통신한다 (계약서: sidecar/README.md).

구조 (MIGRATION_PLAN.md §5 리스크 1 대응):
    Main Thread      : IPC 읽기/쓰기 전담 + 빠른 DB 명령 처리
    ComWorker Thread : ★ Outlook COM 접근 직렬화 (STA 고정 1개)
    Job 스레드        : sync/index 같은 장기 작업 (COM 스레드 경유)

★ 비즈니스 로직은 core/ data/ utils/ 를 무수정 재사용한다 (계획 §4).
"""

__version__ = "1.1.0"
PROTOCOL_VERSION = "1.0"
