"""
OutLook AnyFinder Ver0.9.1.1 for SESUNG Team
[W04] 승인된 동기화 계획 실행 QThread

SyncPlanWorker가 만든 계획을 받아 실제 DB 반영(추가/수정/삭제)을 백그라운드에서 수행한다.
"""

import logging
import time

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class SyncExecuteWorker(QThread):
    progress = pyqtSignal(int, int, str, str)
    speed_update = pyqtSignal(float)
    finished_sync = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    status_changed = pyqtSignal(str)

    def __init__(self, db_path, use_mock: bool, plan, folder_ids=None,
                 include_subfolders=True, after_date=None, incremental=False, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.use_mock = use_mock
        self.plan = plan
        self.folder_ids = folder_ids or [6, 5]
        self.include_subfolders = include_subfolders
        self.after_date = after_date
        self.incremental = incremental
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True
        self.status_changed.emit("stopped")

    def run(self):
        conn = None
        connector = None
        try:
            self.status_changed.emit("running")

            from data.database import init_db
            from core.outlook_connector import create_connector, MockOutlookConnector
            from core.sync_manager import SyncManager, MockSyncManager

            # 스레드 내부에서 별도 DB/COM 연결 생성
            conn = init_db(self.db_path)
            connector = create_connector(use_mock=self.use_mock)
            connector.connect()

            if isinstance(connector, MockOutlookConnector):
                sm = MockSyncManager(conn, connector)
            else:
                sm = SyncManager(conn, connector)

            total_work = (
                len(getattr(self.plan, "new_ids", []))
                + len(getattr(self.plan, "updated_ids", []))
                + len(getattr(self.plan, "deleted_ids", []))
            )
            self.progress.emit(0, total_work, "동기화 준비 중...", "")

            speed_window = []

            def on_progress(done, total, message):
                self.progress.emit(done, total or total_work, message, "")
                now = time.time()
                speed_window.append((now, done))
                while speed_window and now - speed_window[0][0] > 3.0:
                    speed_window.pop(0)
                if len(speed_window) >= 2:
                    dt = speed_window[-1][0] - speed_window[0][0]
                    dc = speed_window[-1][1] - speed_window[0][1]
                    if dt > 0:
                        self.speed_update.emit(dc / dt)

            result = sm.execute_plan(
                self.plan,
                folder_ids=self.folder_ids,
                include_subfolders=self.include_subfolders,
                on_progress=on_progress,
                should_stop=lambda: self._stop_flag,
                after_date=self.after_date,
                incremental=self.incremental,
            )

            if not self._stop_flag:
                self.finished_sync.emit({
                    "added": result.added,
                    "updated": result.updated,
                    "deleted": result.deleted,
                    "skipped": result.skipped,
                    "errors": result.errors,
                    "elapsed_sec": result.elapsed_sec,
                    "message": result.summary,
                })

        except Exception as e:
            logger.error(f"동기화 실행 오류: {e}", exc_info=True)
            if not self._stop_flag:
                self.error_occurred.emit(str(e))
        finally:
            try:
                if connector and hasattr(connector, "close"):
                    connector.close()
            except Exception:
                pass
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

            if not self._stop_flag:
                self.status_changed.emit("completed")
