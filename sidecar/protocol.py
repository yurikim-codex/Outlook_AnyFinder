"""
IPC 프로토콜 — 메시지 빌더와 오류 코드 (MIGRATION_PLAN.md §6)

메시지 포맷 (JSON Lines, 한 줄에 JSON 객체 1개):
    Request   : {"id": 42, "cmd": "search.query", "params": {...}}
    Response  : {"id": 42, "ok": true, "result": {...}}
    Error     : {"id": 42, "ok": false, "error": {"code", "message", "retryable"}}
    Event     : {"event": "sync.progress", "data": {...}}   (id 없음, 비동기 push)
"""


class ErrorCode:
    """표준 오류 코드 — Rust/React가 분기할 수 있는 안정적인 계약."""
    PARSE_ERROR = "PARSE_ERROR"                    # JSON Lines 파싱 실패
    INVALID_PARAMS = "INVALID_PARAMS"              # 필수 파라미터 누락/타입 오류
    UNKNOWN_COMMAND = "UNKNOWN_COMMAND"            # 등록되지 않은 cmd
    DB_NOT_AVAILABLE = "DB_NOT_AVAILABLE"          # DB 열기 실패 (hello는 여전히 동작)
    DB_ERROR = "DB_ERROR"                          # DB 작업 중 오류
    OUTLOOK_CONNECT_FAILED = "OUTLOOK_CONNECT_FAILED"  # Outlook COM 연결 실패
    OUTLOOK_NOT_RUNNING = "OUTLOOK_NOT_RUNNING"    # Outlook 미실행
    JOB_ALREADY_RUNNING = "JOB_ALREADY_RUNNING"    # 다른 장기 작업 실행 중
    JOB_NOT_RUNNING = "JOB_NOT_RUNNING"            # 취소할 작업이 없음
    PLAN_NOT_FOUND = "PLAN_NOT_FOUND"              # sync.execute용 plan_id 만료/없음
    NOT_SUPPORTED = "NOT_SUPPORTED"                # 현재 모드(예: Mock)에서 미지원
    INTERNAL = "INTERNAL"                          # 그 외 모든 내부 오류


_DEFAULT_RETRYABLE = {
    ErrorCode.PARSE_ERROR: False,
    ErrorCode.INVALID_PARAMS: False,
    ErrorCode.UNKNOWN_COMMAND: False,
    ErrorCode.DB_NOT_AVAILABLE: True,
    ErrorCode.DB_ERROR: True,
    ErrorCode.OUTLOOK_CONNECT_FAILED: True,
    ErrorCode.OUTLOOK_NOT_RUNNING: True,
    ErrorCode.JOB_ALREADY_RUNNING: True,
    ErrorCode.JOB_NOT_RUNNING: False,
    ErrorCode.PLAN_NOT_FOUND: False,
    ErrorCode.NOT_SUPPORTED: False,
    ErrorCode.INTERNAL: False,
}


class SidecarError(Exception):
    """계약된 오류 코드를 가진 사이드카 예외."""

    def __init__(self, code: str, message: str, retryable: bool = None, details: dict = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = _DEFAULT_RETRYABLE.get(code, False) if retryable is None else bool(retryable)
        self.details = details or {}


class _AsyncMarker:
    """핸들러가 이 값을 반환하면 응답은 작업 완료 콜백이 나중에 보낸다."""
    __slots__ = ()

    def __repr__(self):
        return "<ASYNC>"


ASYNC = _AsyncMarker()


def ok_response(req_id, result) -> dict:
    return {"id": req_id, "ok": True, "result": result}


def error_response(req_id, code: str, message: str, retryable: bool = False, details: dict = None) -> dict:
    error = {"code": code, "message": message, "retryable": bool(retryable)}
    if details:
        error["details"] = details
    return {"id": req_id, "ok": False, "error": error}


def event_message(name: str, data: dict = None) -> dict:
    return {"event": name, "data": data if data is not None else {}}


def classify_exception(exc: Exception) -> SidecarError:
    """임의 예외를 계약된 SidecarError로 변환한다."""
    if isinstance(exc, SidecarError):
        return exc
    name = type(exc).__name__
    text = str(exc)
    # core.outlook_connector.OutlookConnectionError → OUTLOOK_CONNECT_FAILED
    if name == "OutlookConnectionError":
        return SidecarError(ErrorCode.OUTLOOK_CONNECT_FAILED, text)
    if "database is locked" in text.lower():
        return SidecarError(ErrorCode.DB_ERROR, text)
    return SidecarError(ErrorCode.INTERNAL, f"{name}: {text}")
