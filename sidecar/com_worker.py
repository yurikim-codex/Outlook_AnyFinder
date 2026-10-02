"""
Outlook COM 전담 STA 스레드 + Job Queue (MIGRATION_PLAN.md §5 리스크 1 대응).

원칙: Outlook COM 객체의 생성/접근은 오직 이 스레드에서만 일어난다.
    - pythoncom.CoInitialize() 1회 (Windows 실모드)
    - 모든 COM 작업은 submit(fn)으로 직렬화 → RPC_E_WRONG_THREAD /
      CO_E_NOTINITIALIZED 류 간헐 오류 원천 차단
    - 검색(SQLite FTS5)은 이 스레드를 쓰지 않는다 → 동기화 중에도 즉시 응답

Mock/비-Windows 환경에서도 동일한 직렬화 구조를 유지한다 (행동 동등성 테스트 가능).
"""

import logging
import queue
import sys
import threading
from concurrent.futures import Future

logger = logging.getLogger("sidecar.com")

_SHUTDOWN = object()


class ComWorker:
    """단일 STA 스레드 작업 실행기."""

    def __init__(self, use_mock: bool):
        self.use_mock = use_mock
        self._queue = queue.Queue()
        self._thread = None
        self._stop = threading.Event()
        self._co_initialized = False
        self.connector = None

    # ── 생명주기 ──

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="ComWorkerSTA", daemon=True)
        self._thread.start()

    @property
    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def submit(self, fn) -> Future:
        """COM 스레드에서 실행할 작업을 큐에 넣는다. Future는 즉시 반환."""
        if not self.alive:
            self.start()
        fut = Future()
        self._queue.put((fn, fut))
        return fut

    def shutdown(self, timeout: float = 5.0):
        self._stop.set()
        self._queue.put(_SHUTDOWN)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    # ── 내부 ──

    def _run(self):
        self._co_initialize()
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is _SHUTDOWN:
                break
            fn, fut = item
            if fut.set_running_or_notify_cancel():
                try:
                    fut.set_result(fn())
                except BaseException as e:  # noqa: BLE001 — Future로 전달해야 함
                    fut.set_exception(e)
        self._close_connector()
        self._co_uninitialize()
        logger.info("ComWorker 스레드 종료")

    def _co_initialize(self):
        if self.use_mock or sys.platform != "win32":
            logger.info("ComWorker: COM 초기화 생략 (mock/비Windows) — 직렬화 구조는 유지")
            return
        try:
            import pythoncom
            pythoncom.CoInitialize()
            self._co_initialized = True
            logger.info("ComWorker: CoInitialize 완료 (STA)")
        except Exception as e:
            logger.error(f"ComWorker: CoInitialize 실패: {e}")

    def _co_uninitialize(self):
        if self._co_initialized:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass
            self._co_initialized = False

    def _close_connector(self):
        if self.connector is not None:
            try:
                self.connector.close()
            except Exception:
                pass
            self.connector = None

    def get_connector(self):
        """Outlook 커넥터를 (COM 스레드 내부에서!) 가져온다. 필요 시 생성/연결.

        주의: 이 메서드는 submit()된 작업 내부에서만 호출해야 한다.
        """
        connected = False
        try:
            connected = bool(self.connector and self.connector.is_connected)
        except Exception:
            connected = False
        if not connected:
            from core.outlook_connector import create_connector
            self._close_connector()
            self.connector = create_connector(use_mock=self.use_mock)
            self.connector.connect()
            logger.info(f"Outlook 커넥터 연결 완료 (mock={self.use_mock})")
        return self.connector
