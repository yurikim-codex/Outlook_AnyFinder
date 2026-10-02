"""
장기 작업 실행 헬퍼 — COM 스레드 실행 + 완료 콜백 응답.

두 가지 경로:
    run_job(ctx, kind, job_fn)   : JobRegistry에 등록 (취소 가능 — sync/index)
    run_on_com(ctx, fn)          : 등록 없이 COM 스레드에서 1회 실행 (mail.open 등)

두 경로 모두 응답은 Future 완료 콜백이 Channel로 보낸다 (메인 루프는 블로킹 없음).
"""

import logging

from .protocol import ASYNC, ErrorCode, SidecarError, classify_exception

logger = logging.getLogger("sidecar.jobs")


def _wire_response(ctx, fut, req_id):
    """Future 완료 시 응답/오류를 채널로 전송."""
    channel = ctx["channel"]

    def done(f):
        try:
            if f.cancelled():
                channel.send_error(req_id, ErrorCode.INTERNAL, "작업이 취소되었습니다")
                return
            exc = f.exception()
            if exc is None:
                channel.send_ok(req_id, f.result())
            else:
                err = classify_exception(exc)
                logger.error(f"작업 오류: {err.code}: {err.message}")
                channel.send_error(req_id, err.code, err.message, err.retryable, err.details or None)
                try:
                    channel.send_event("error", {"code": err.code, "message": err.message})
                except Exception:
                    pass
        except Exception:
            logger.exception("작업 응답 전송 실패")

    fut.add_done_callback(done)


def run_job(ctx, kind: str, job_fn):
    """취소 가능한 장기 작업. job_fn(job)은 COM 스레드에서 실행된다.

    Returns: ASYNC 마커 (응답은 완료 콜백이 전송)
    """
    state = ctx["state"]
    req_id = ctx["id"]
    job = state.jobs.begin(kind, req_id)

    def wrapped():
        try:
            return job_fn(job)
        finally:
            state.jobs.finish(job)

    fut = state.com.submit(wrapped)
    _wire_response(ctx, fut, req_id)
    return ASYNC


def run_on_com(ctx, fn):
    """COM 스레드에서 실행하지만 JobRegistry에는 등록하지 않는 가벼운 작업.

    동기화 중에도 큐잉되어 순차 실행된다 (STA 직렬화 원칙 유지).
    """
    state = ctx["state"]
    req_id = ctx["id"]
    fut = state.com.submit(fn)
    _wire_response(ctx, fut, req_id)
    return ASYNC


def require_str(params: dict, key: str, allow_empty: bool = False) -> str:
    value = params.get(key)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise SidecarError(
            ErrorCode.INVALID_PARAMS,
            f"파라미터 '{key}'은(는) 비어있지 않은 문자열이어야 합니다",
        )
    return value


def require_int(params: dict, key: str, default: int = None, minimum: int = None, maximum: int = None) -> int:
    value = params.get(key, default)
    if value is None:
        raise SidecarError(ErrorCode.INVALID_PARAMS, f"파라미터 '{key}'이(가) 필요합니다")
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise SidecarError(ErrorCode.INVALID_PARAMS, f"파라미터 '{key}'은(는) 정수여야 합니다: {value!r}")
    if minimum is not None and value < minimum:
        raise SidecarError(ErrorCode.INVALID_PARAMS, f"파라미터 '{key}'은(는) {minimum} 이상이어야 합니다")
    if maximum is not None and value > maximum:
        value = maximum
    return value
