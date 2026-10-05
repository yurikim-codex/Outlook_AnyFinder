"""system.* — 핸드셰이크 / 헬스체크 / 종료."""

import logging
import os
import sys
from datetime import datetime

logger = logging.getLogger("sidecar.handlers.system")


def register(dispatcher):
    dispatcher.register("system.hello", hello)
    dispatcher.register("system.ping", ping)
    dispatcher.register("system.shutdown", shutdown)
    dispatcher.register("system.commands", commands)
    dispatcher.register("system.info", info)
    dispatcher.register("system.debug.print", debug_print)


def hello(state, params, ctx):
    """핸드셰이크 — DB가 깨져 있어도 반드시 성공해야 한다 (계획 Phase 1 완료 기준)."""
    from sidecar import PROTOCOL_VERSION, __version__

    db_ok = False
    db_error = state.db_error
    try:
        state.require_db()
        db_ok = True
        db_error = None
    except Exception as e:
        db_error = str(e)

    if state.use_mock:
        outlook_ok, outlook_note = True, "mock connector"
    else:
        try:
            from core.outlook_connector import HAS_WIN32, WIN32_IMPORT_ERROR
            outlook_ok = bool(HAS_WIN32)
            outlook_note = "pywin32 importable" if outlook_ok else f"pywin32 import failed: {WIN32_IMPORT_ERROR}"
        except Exception as e:
            outlook_ok, outlook_note = False, str(e)

    return {
        "sidecar_version": __version__,
        "protocol_version": PROTOCOL_VERSION,
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "pid": os.getpid(),
        "use_mock": state.use_mock,
        "db_path": str(state.db_path),
        "db_ok": db_ok,
        "db_error": db_error,
        "outlook_ok": outlook_ok,
        "outlook_note": outlook_note,
        "commands_count": len(ctx["dispatcher"]),
        "started_at": datetime.fromtimestamp(state.started_at).isoformat(timespec="seconds"),
        "utf8_io": state.utf8_report,
        "stdout_protected": state.stdout_protected,
    }


def ping(state, params, ctx):
    return {"pong": True, "ts": datetime.now().isoformat(timespec="milliseconds")}


def info(state, params, ctx):
    """경량 버전/환경 조회 — 프런트엔드 버전 불일치 감지용 (계획 Phase 4-4).

    hello와 달리 DB 상태를 건드리지 않는다 (schema_version은 best-effort).
    """
    from sidecar import PROTOCOL_VERSION, __version__

    schema_version = None
    try:
        def work(conn):
            row = conn.execute(
                "SELECT value FROM sync_meta WHERE key='schema_version'"
            ).fetchone()
            return row["value"] if row else None

        schema_version = state.in_db(work)
    except Exception:
        schema_version = None

    return {
        "sidecar_version": __version__,
        "protocol_version": PROTOCOL_VERSION,
        "schema_version": schema_version,
        "commands_count": len(ctx["dispatcher"]),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "mock": state.use_mock,
        "data_dir": str(state.data_dir),
        "db_path": str(state.db_path),
    }


def shutdown(state, params, ctx):
    """정상 종료 — 응답 전송 후 IpcServer가 루프를 끝낸다."""
    logger.info("system.shutdown 요청 수신 — 정상 종료합니다")
    return {"ok": True, "message": "사이드카를 종료합니다"}


def commands(state, params, ctx):
    cmds = ctx["dispatcher"].commands()
    return {"commands": cmds, "count": len(cmds)}


def debug_print(state, params, ctx):
    """stdout 오염 방어 검증용 (계획 §5 리스크 2 검증).

    Python 레벨 print와 fd 레벨 write를 모두 시도한다.
    보호 ON이면 둘 다 프로토콜 채널에 도달할 수 없다.
    """
    text = str(params.get("text", "stdout 오염 테스트 🚨 print contamination"))
    try:
        print(text)  # sys.stdout → stderr로 리다이렉트됨 (보호 ON)
    except Exception:
        pass
    try:
        os.write(1, (text + "\n").encode("utf-8", errors="replace"))  # fd 1 → devnull (보호 ON)
    except Exception:
        pass
    return {"ok": True, "printed": text, "stdout_protected": state.stdout_protected}
