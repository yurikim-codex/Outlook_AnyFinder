"""
장기 실행 작업 레지스트리 — sync.plan / sync.execute / sync.run / index.build.

작업이 COM 스레드에서 도는 동안에도 메인 스레드는 stdin을 계속 읽으므로
search.query(즉시 응답)와 sync.cancel(중지 요청)이 항상 동작한다.
"""

import threading
import time
import uuid

from .protocol import ErrorCode, SidecarError


class Job:
    def __init__(self, kind: str, req_id=None):
        self.id = uuid.uuid4().hex[:8]
        self.kind = kind
        self.req_id = req_id
        self.started_at = time.time()
        self.stop_event = threading.Event()

    def should_stop(self) -> bool:
        return self.stop_event.is_set()

    def request_stop(self):
        self.stop_event.set()

    def to_dict(self) -> dict:
        return {
            "job_id": self.id,
            "kind": self.kind,
            "req_id": self.req_id,
            "started_at": self.started_at,
            "elapsed_sec": round(time.time() - self.started_at, 2),
            "stop_requested": self.stop_event.is_set(),
        }


class JobRegistry:
    """동시 장기 작업은 1개로 제한한다 (Outlook COM 직렬화 + DB lock 방지)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._current = None

    def begin(self, kind: str, req_id=None) -> Job:
        with self._lock:
            if self._current is not None:
                raise SidecarError(
                    ErrorCode.JOB_ALREADY_RUNNING,
                    f"이미 '{self._current.kind}' 작업이 실행 중입니다 — 완료/취소 후 다시 시도하세요",
                    details=self._current.to_dict(),
                )
            job = Job(kind, req_id)
            self._current = job
            return job

    def finish(self, job: Job):
        with self._lock:
            if self._current is job:
                self._current = None

    def cancel(self) -> Job:
        with self._lock:
            if self._current is None:
                raise SidecarError(
                    ErrorCode.JOB_NOT_RUNNING,
                    "취소할 동기화/인덱싱 작업이 실행 중이 아닙니다",
                )
            job = self._current
        job.request_stop()
        return job

    def current(self):
        with self._lock:
            return self._current
