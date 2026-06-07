"""
OutLook AnyFinder Ver0.9.1.1 for SESUNG Team
[W02] 증분 동기화 QThread (v3 — 스레드 내 DB+COM 새 생성)
"""

import logging
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class SyncWorker(QThread):
    sync_progress = pyqtSignal(int, int, str)
    sync_finished = pyqtSignal(dict)
    sync_error = pyqtSignal(str)

    def __init__(self, db_path, use_mock: bool, folder_ids=None,
                 include_subfolders=True, after_date=None, incremental=False, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.use_mock = use_mock
        self.folder_ids = folder_ids or [6, 5]
        self.include_subfolders = include_subfolders
        self.after_date = after_date
        self.incremental = incremental

    def run(self):
        conn = None
        connector = None
        try:
            # ★ 스레드 내에서 새 DB 연결
            from data.database import init_db
            conn = init_db(self.db_path)

            # ★ 스레드 내에서 새 COM 연결
            from core.outlook_connector import create_connector
            connector = create_connector(use_mock=self.use_mock)
            connector.connect()

            from core.sync_manager import SyncManager, MockSyncManager
            from core.outlook_connector import MockOutlookConnector

            if isinstance(connector, MockOutlookConnector):
                sm = MockSyncManager(conn, connector)
            else:
                sm = SyncManager(conn, connector)

            self.sync_progress.emit(0, 0, "메일 비교 중...")

            plan = sm.create_plan(
                folder_ids=self.folder_ids,
                include_subfolders=self.include_subfolders,
                on_status=lambda msg: self.sync_progress.emit(0, 0, msg),
                after_date=self.after_date,
                incremental=self.incremental,
                on_scan_progress=lambda d, t, m, f: self.sync_progress.emit(d, t, m),
            )

            if not plan.has_changes:
                self.sync_finished.emit({
                    "added": 0, "updated": 0, "deleted": 0,
                    "skipped": plan.skipped_count, "errors": 0,
                    "message": f"✅ 변경 없음 — {plan.skipped_count:,}건 최신 상태"
                })
                conn.close()
                return

            result = sm.execute_plan(
                plan, folder_ids=self.folder_ids,
                include_subfolders=self.include_subfolders,
                on_progress=lambda d, t, m: self.sync_progress.emit(d, t, m),
                after_date=self.after_date,
                incremental=self.incremental,
            )

            self.sync_finished.emit({
                "added": result.added, "updated": result.updated,
                "deleted": result.deleted, "skipped": result.skipped,
                "errors": result.errors, "elapsed_sec": result.elapsed_sec,
                "message": result.summary,
            })

            conn.close()
            conn = None

        except Exception as e:
            logger.error(f"동기화 오류: {e}", exc_info=True)
            self.sync_error.emit(str(e))
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
