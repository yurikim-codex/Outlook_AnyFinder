"""
OutLook AnyFinder Python Sidecar 엔트리포인트.

실행:
    python -m sidecar --mock                 # 개발/테스트 (Mock Outlook)
    python -m sidecar                        # Windows: 실 Outlook COM
    OutlookAnyFinderSidecar.exe              # PyInstaller onedir 빌드 (build_sidecar.ps1)

★ STEP 순서가 중요하다 (MIGRATION_PLAN.md §5 리스크 2):
    STEP 0  최소 import + 인수 파싱 (argparse 미사용 — stdout 오염 원천 차단)
    STEP 1  stdio 가드 — UTF-8 강제 + stdout 보호 (어떤 비즈니스 import보다 먼저!)
    STEP 2  로깅 설정 — 파일 + stderr 전용 (stdout 핸들러 절대 금지)
    STEP 3  비즈니스 로직 import (bs4/pywin32 경고도 stderr로만 간다)
    STEP 4  상태 구축 (DB/COM 워커) — DB 실패해도 종료하지 않음
    STEP 5  디스패처 + 핸들러 등록
    STEP 6  ready 이벤트 발송
    STEP 7  시그널 핸들러 (SIGTERM/SIGINT, Windows SIGBREAK)
    STEP 8  IPC 서브 루프
    STEP 9  정상 종료 정리
"""

# ═══ STEP 0: 최소 import + 인수 파싱 ═══
import os
import sys

# 스크립트 직접 실행(PyInstaller 등) 시에도 sidecar 패키지를 찾을 수 있게 보장
_PKG_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)


def _parse_args(argv):
    """argparse를 쓰지 않는 수동 파싱 — usage/help가 stdout으로 새는 것을 원천 차단."""
    opts = {
        "mock": False,
        "data_dir": None,
        "db_path": None,
        "log_level": "INFO",
        "protect_stdout": True,
        "help": False,
        "version": False,
    }
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--mock":
            opts["mock"] = True
        elif arg == "--no-stdout-protect":
            opts["protect_stdout"] = False
        elif arg in ("--help", "-h"):
            opts["help"] = True
        elif arg in ("--version", "-V"):
            opts["version"] = True
        elif arg == "--data-dir" and i + 1 < len(argv):
            i += 1
            opts["data_dir"] = argv[i]
        elif arg.startswith("--data-dir="):
            opts["data_dir"] = arg.split("=", 1)[1]
        elif arg == "--db-path" and i + 1 < len(argv):
            i += 1
            opts["db_path"] = argv[i]
        elif arg.startswith("--db-path="):
            opts["db_path"] = arg.split("=", 1)[1]
        elif arg == "--log-level" and i + 1 < len(argv):
            i += 1
            opts["log_level"] = argv[i]
        elif arg.startswith("--log-level="):
            opts["log_level"] = arg.split("=", 1)[1]
        # 알 수 없는 인수는 무시 (방어적)
        i += 1
    return opts


_OPTS = _parse_args(sys.argv[1:])

# ═══ STEP 1: stdio 가드 (가장 먼저!) ═══
from sidecar.stdio_guard import force_utf8_io, protect_stdout  # noqa: E402

_UTF8_REPORT = force_utf8_io()
_PROTO_STREAM = protect_stdout(enabled=_OPTS["protect_stdout"])

# ═══ STEP 2: 로깅 (파일 + stderr 전용) ═══
import logging  # noqa: E402
from logging.handlers import RotatingFileHandler  # noqa: E402
from pathlib import Path  # noqa: E402


def _default_data_dir() -> Path:
    return Path(os.environ.get("ANYFINDER_DATA_DIR") or (Path.home() / ".outlook_anyfinder"))


def _setup_logging(log_dir: Path, level_name: str):
    level = getattr(logging, str(level_name).upper(), logging.INFO)
    handlers = [logging.StreamHandler(sys.stderr)]  # ★ stdout 핸들러 절대 금지
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(
            log_dir / "sidecar.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"))
    except Exception:
        pass
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )


if _OPTS["help"]:
    print(__doc__, file=sys.stderr)
    sys.exit(0)
if _OPTS["version"]:
    from sidecar import __version__
    print(f"OutlookAnyFinderSidecar {__version__}", file=sys.stderr)
    sys.exit(0)

_DATA_DIR = Path(_OPTS["data_dir"]).expanduser() if _OPTS["data_dir"] else _default_data_dir()
_DB_PATH = Path(_OPTS["db_path"]).expanduser() if _OPTS["db_path"] else (_DATA_DIR / "anyfinder.db")

_setup_logging(_DATA_DIR / "logs", _OPTS["log_level"])
logger = logging.getLogger("sidecar.main")
logger.info(f"사이드카 시작 — utf8_io={_UTF8_REPORT}, stdout_protect={_OPTS['protect_stdout']}")

# ═══ STEP 3: 비즈니스 로직 import ═══
# (이 시점 이후의 import 경고/출력은 모두 stderr로만 간다)

# ═══ STEP 4~9: 메인 ═══

def main() -> int:
    from sidecar import PROTOCOL_VERSION, __version__
    from sidecar.dispatcher import Dispatcher
    from sidecar.handlers import register_all
    from sidecar.ipc import Channel, IpcServer
    from sidecar.state import SidecarState

    use_mock = bool(_OPTS["mock"] or os.environ.get("ANYFINDER_MOCK") == "1" or sys.platform != "win32")
    if sys.platform != "win32" and not _OPTS["mock"]:
        logger.info("비Windows 플랫폼 — 자동으로 Mock 모드 사용")

    # STEP 4: 상태 (DB 실패해도 계속 진행 — hello는 DB 없이도 성공해야 함)
    state = SidecarState(
        data_dir=_DATA_DIR,
        db_path=_DB_PATH,
        use_mock=use_mock,
        utf8_report=_UTF8_REPORT,
        stdout_protected=_OPTS["protect_stdout"],
    )

    # STEP 5: 디스패처
    dispatcher = register_all(Dispatcher())
    logger.info(f"명령 {len(dispatcher)}개 등록 완료")

    channel = Channel(_PROTO_STREAM)
    server = IpcServer(dispatcher, channel, state)

    # STEP 6: 시그널 핸들러 — ready 이벤트보다 먼저 등록한다.
    # (ready를 보고 받은 부모가 즉시 SIGTERM/CTRL_BREAK를 보내도 핸들러가 준비되어 있어야
    #  정상 종료(exit 0)된다 — ready 먼저 보내면 등록 전 시그널에 기본 동작(-15)으로 죽는다)
    import signal

    def _graceful(signum, _frame):
        logger.info(f"시그널 {signum} 수신 — 정상 종료 시작")
        server.request_shutdown()

    signal.signal(signal.SIGTERM, _graceful)
    signal.signal(signal.SIGINT, _graceful)
    if hasattr(signal, "SIGBREAK"):
        # Windows CTRL_BREAK_EVENT (Rust가 CREATE_NEW_PROCESS_GROUP으로 spawn 시 사용)
        signal.signal(signal.SIGBREAK, _graceful)

    # STEP 7: ready 이벤트 — React 셸은 이 이벤트를 보고 입력을 활성화한다
    channel.send_event("ready", {
        "sidecar_version": __version__,
        "protocol_version": PROTOCOL_VERSION,
        "pid": os.getpid(),
        "use_mock": use_mock,
        "db_ok": state.conn is not None,
        "commands_count": len(dispatcher),
        "utf8_io": _UTF8_REPORT,
    })

    # STEP 8: IPC 루프
    try:
        server.serve_forever()
    except Exception:
        logger.exception("IPC 서버 비정상 종료")
        return 1
    finally:
        # STEP 9: 정리 — 좀비/누수 방지
        logger.info("사이드카 종료 정리 중...")
        try:
            state.close()
        except Exception:
            logger.exception("종료 정리 오류")
        try:
            _PROTO_STREAM.flush()
        except Exception:
            pass
    logger.info("사이드카 정상 종료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
