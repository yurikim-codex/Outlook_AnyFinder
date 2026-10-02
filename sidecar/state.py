"""
사이드카 런타임 상태 — DB(공유 연결+lock), COM 워커, 작업 레지스트리, 계획 캐시.

DB 소유권 규칙 (MIGRATION_PLAN.md §5 리스크 4):
    [쓰기] Python 사이드카 단독 소유. Rust/React는 직접 쓰지 않는다.
    빠른 명령(search/bookmark/settings)은 공유 연결 + RLock으로 직렬화,
    장기 작업(sync/index)은 작업 스레드 전용 연결을 따로 연다 (WAL 모드라 공존 가능).
"""

import json
import logging
import sqlite3
import threading
import time
from collections import OrderedDict
from pathlib import Path

from .com_worker import ComWorker
from .jobs import JobRegistry
from .protocol import ErrorCode, SidecarError

logger = logging.getLogger("sidecar.state")

SCHEMA_VERSION = 1  # sync_meta.schema_version — 사이드카/프론트 스키마 불일치 감지용


class SidecarState:
    def __init__(self, data_dir: Path, db_path: Path, use_mock: bool,
                 utf8_report: dict = None, stdout_protected: bool = True):
        self.data_dir = Path(data_dir)
        self.db_path = Path(db_path)
        self.config_path = self.data_dir / "config.json"
        self.use_mock = use_mock
        self.utf8_report = utf8_report or {}
        self.stdout_protected = stdout_protected
        self.started_at = time.time()

        self.db_lock = threading.RLock()
        self.conn = None
        self.db_error = None

        self.com = ComWorker(use_mock)
        self.jobs = JobRegistry()

        # sync.plan → (사용자 승인) → sync.execute 흐름용 계획 캐시
        self._plans = OrderedDict()   # plan_id -> SyncPlan
        self._plans_lock = threading.Lock()
        self._max_plans = 5

        self._open_db()
        self.com.start()

    # ── DB ──

    def _open_db(self):
        try:
            from data.database import init_db
            self.conn = init_db(self.db_path)
            self.db_error = None
            self._ensure_schema_version(self.conn)
            logger.info(f"DB 준비 완료: {self.db_path}")
        except Exception as e:
            self.conn = None
            self.db_error = f"{type(e).__name__}: {e}"
            # ★ DB가 깨져도 사이드카는 죽지 않는다 — system.hello 등은 계속 동작
            logger.error(f"DB 초기화 실패 (제한된 명령으로 계속 동작): {self.db_error}")

    @staticmethod
    def _ensure_schema_version(conn: sqlite3.Connection):
        try:
            from data.database import get_meta, set_meta
            if get_meta(conn, "schema_version", None) is None:
                set_meta(conn, "schema_version", str(SCHEMA_VERSION))
        except Exception as e:
            logger.debug(f"schema_version 기록 실패(무시): {e}")

    def require_db(self) -> sqlite3.Connection:
        """공유 DB 연결 반환. 없으면 1회 재시도 후 DB_NOT_AVAILABLE 오류."""
        with self.db_lock:
            if self.conn is None:
                self._open_db()
            if self.conn is None:
                raise SidecarError(
                    ErrorCode.DB_NOT_AVAILABLE,
                    f"DB를 사용할 수 없습니다: {self.db_error}",
                )
            return self.conn

    def in_db(self, fn, *args, **kwargs):
        """공유 연결 + lock 안에서 DB 작업 실행."""
        with self.db_lock:
            return fn(self.require_db(), *args, **kwargs)

    def job_conn(self) -> sqlite3.Connection:
        """장기 작업 스레드 전용 새 연결 (사용 후 작업에서 close 책임)."""
        from data.database import init_db
        conn = init_db(self.db_path)
        self._ensure_schema_version(conn)
        return conn

    # ── sync plan 캐시 ──

    def put_plan(self, plan_id: str, plan):
        with self._plans_lock:
            self._plans[plan_id] = plan
            while len(self._plans) > self._max_plans:
                self._plans.popitem(last=False)

    def get_plan(self, plan_id: str):
        with self._plans_lock:
            plan = self._plans.get(plan_id)
        if plan is None:
            raise SidecarError(
                ErrorCode.PLAN_NOT_FOUND,
                f"동기화 계획을 찾을 수 없습니다 (plan_id={plan_id}) — sync.plan을 다시 실행하세요",
            )
        return plan

    # ── 설정 (config.json) ──

    def load_settings(self) -> dict:
        from utils.config import DEFAULT_CONFIG
        try:
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
                return deep_merge(DEFAULT_CONFIG, user_config)
        except Exception as e:
            logger.warning(f"설정 로드 실패 — 기본값 사용: {e}")
        return json.loads(json.dumps(DEFAULT_CONFIG))  # 깊은 복사

    def save_settings(self, config: dict):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    # ── 종료 ──

    def close(self):
        try:
            self.com.shutdown(timeout=5.0)
        except Exception:
            pass
        with self.db_lock:
            if self.conn is not None:
                try:
                    self.conn.close()
                except Exception:
                    pass
                self.conn = None


def deep_merge(base: dict, override: dict) -> dict:
    """딕셔너리 깊은 머지 (utils.config._deep_merge와 동일한 의미론, sidecar 독립 유지)."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
