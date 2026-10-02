"""
JSON Lines IPC 서버 — stdin 읽기 루프 + 스레드 안전 stdout 채널.

설계:
- Channel  : 프로토콜 전용 스트림에 대한 유일한 writer (lock 보호).
             어떤 스레드(메인/COM/작업)에서도 안전하게 응답·이벤트를 보낼 수 있다.
- IpcServer: stdin은 별도 reader 스레드가 읽어 큐에 넣는다.
             메인 루프는 큐를 0.2s 타임아웃으로 poll → shutdown 이벤트/시그널에
             stdin readline 블로킹과 무관하게 항상 반응할 수 있다
             (계획 Phase 1 회귀 테스트 test_07 대응).
- 방어 파서: JSON 파싱 실패 줄은 로그로 흘려보내고 PARSE_ERROR 응답 후 계속 진행
             (계획 §5 리스크 2 — 크래시 금지).
"""

import json
import logging
import queue
import sys
import threading

from .protocol import (
    ASYNC, ErrorCode, SidecarError, classify_exception,
    error_response, event_message, ok_response,
)
from .serialize import to_jsonable

logger = logging.getLogger("sidecar.ipc")

_EOF = object()


class Channel:
    """스레드 안전 JSON Lines writer. 프로토콜 스트림은 오직 여기에서만 쓴다."""

    def __init__(self, stream):
        self._stream = stream
        self._lock = threading.Lock()
        self.broken = False

    def send(self, message: dict) -> bool:
        if self.broken:
            return False
        try:
            line = json.dumps(to_jsonable(message), ensure_ascii=False) + "\n"
            with self._lock:
                self._stream.write(line)
                self._stream.flush()
            return True
        except Exception as e:
            # 채널이 죽어도(부모 프로세스 종료 등) 사이드카 루프는 살아 있어야 한다
            self.broken = True
            logger.error(f"IPC 쓰기 실패 — 채널을 비활성화합니다: {e}")
            return False

    def send_ok(self, req_id, result) -> bool:
        return self.send(ok_response(req_id, result))

    def send_error(self, req_id, code: str, message: str, retryable: bool = False, details: dict = None) -> bool:
        return self.send(error_response(req_id, code, message, retryable, details))

    def send_error_exc(self, req_id, exc: Exception) -> bool:
        err = classify_exception(exc)
        return self.send_error(req_id, err.code, err.message, err.retryable, err.details or None)

    def send_event(self, name: str, data: dict = None) -> bool:
        return self.send(event_message(name, data))


class IpcServer:
    """stdin → dispatcher → stdout JSON Lines 루프."""

    def __init__(self, dispatcher, channel: Channel, state):
        self.dispatcher = dispatcher
        self.channel = channel
        self.state = state
        self._lines = queue.Queue()
        self._shutdown = threading.Event()
        self._reader = None

    # ── 생명주기 ──

    def request_shutdown(self):
        self._shutdown.set()

    @property
    def shutting_down(self) -> bool:
        return self._shutdown.is_set()

    def serve_forever(self):
        self._reader = threading.Thread(target=self._read_stdin, name="StdinReader", daemon=True)
        self._reader.start()
        logger.info("IPC 서버 시작 — stdin 읽는 중")
        while not self._shutdown.is_set():
            try:
                item = self._lines.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is _EOF:
                logger.info("stdin EOF — 부모 프로세스 종료 감지, 사이드카 종료")
                break
            self._handle_line(item)
        self._shutdown.set()

    def _read_stdin(self):
        while True:
            try:
                line = sys.stdin.readline()
            except Exception as e:
                logger.error(f"stdin 읽기 오류: {e}")
                break
            if not line:
                self._lines.put(_EOF)
                return
            self._lines.put(line)

    # ── 처리 ──

    def _handle_line(self, line: str):
        line = line.strip()
        if not line:
            return
        try:
            msg = json.loads(line)
        except Exception:
            # ★ 방어 파서: 비-JSON 줄은 무시하고 진행 (프로토콜 죽음 방지)
            logger.warning(f"비-JSON 프로토콜 줄 무시: {line[:200]!r}")
            self.channel.send(error_response(
                None, ErrorCode.PARSE_ERROR,
                "JSON Lines 파싱 실패 — 해당 줄을 무시하고 계속 동작합니다",
                details={"line": line[:200]},
            ))
            return
        if not isinstance(msg, dict):
            self.channel.send(error_response(
                None, ErrorCode.PARSE_ERROR, "프로토콜 메시지는 JSON 객체여야 합니다"))
            return

        req_id = msg.get("id")
        cmd = msg.get("cmd")
        if not isinstance(cmd, str) or not cmd.strip():
            self.channel.send_error(req_id, ErrorCode.INVALID_PARAMS, "'cmd' 필드가 없거나 비어 있습니다")
            return
        params = msg.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            self.channel.send_error(req_id, ErrorCode.INVALID_PARAMS, "'params'는 JSON 객체여야 합니다")
            return

        ctx = {
            "id": req_id,
            "channel": self.channel,
            "server": self,
            "state": self.state,
            "dispatcher": self.dispatcher,
        }
        try:
            result = self.dispatcher.dispatch(cmd.strip(), params, ctx)
            if result is ASYNC:
                # 응답은 작업 완료 콜백이 나중에 보낸다 (run_async 참조)
                return
            self.channel.send_ok(req_id, result)
        except SidecarError as e:
            self.channel.send_error(req_id, e.code, e.message, e.retryable, e.details or None)
        except Exception as e:
            logger.exception(f"명령 처리 오류: {cmd}")
            self.channel.send_error_exc(req_id, e)
        finally:
            if cmd.strip() == "system.shutdown" and not self._shutdown.is_set():
                # 응답이 전송된 뒤 루프를 끝낸다
                self.request_shutdown()
