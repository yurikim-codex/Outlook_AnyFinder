"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[W03] 동기화 계획 생성 QThread

Outlook 전체/선택 폴더 스캔과 DB 비교(create_plan)는 시간이 오래 걸릴 수 있으므로
메인 UI 스레드가 아닌 별도 스레드에서 수행한다.
"""

import logging

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class SyncPlanWorker(QThread):
    """동기화 승인 전에 필요한 '변경 사항 비교' 전용 워커."""

    plan_progress = pyqtSignal(str)
    plan_scan_progress = pyqtSignal(int, int, str, str)
    plan_ready = pyqtSignal(object)      # core.sync_manager.SyncPlan
    plan_error = pyqtSignal(str)

    def __init__(self, db_path, use_mock: bool, folder_ids=None,
                 include_subfolders=True, after_date=None, incremental=False,
                 mail_after_date=None, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.use_mock = use_mock
        self.folder_ids = folder_ids or [6, 5]
        self.include_subfolders = include_subfolders
        self.after_date = after_date
        self.incremental = incremental
        self.mail_after_date = mail_after_date
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def run(self):
        conn = None
        connector = None
        try:
            from data.database import init_db
            from core.outlook_connector import create_connector, MockOutlookConnector
            from core.sync_manager import SyncManager, MockSyncManager

            self.plan_progress.emit("Outlook 연결 중...")

            # 스레드 내부에서 별도 DB/COM 연결 생성
            conn = init_db(self.db_path)
            connector = create_connector(use_mock=self.use_mock)
            connector.connect()

            if isinstance(connector, MockOutlookConnector):
                sm = MockSyncManager(conn, connector)
            else:
                sm = SyncManager(conn, connector)

            self.plan_progress.emit("Outlook 메일 목록 비교 중...")
            plan = sm.create_plan(
                folder_ids=self.folder_ids,
                include_subfolders=self.include_subfolders,
                on_status=self.plan_progress.emit,
                should_stop=lambda: self._stop_flag,
                after_date=self.after_date,
                incremental=self.incremental,
                mail_after_date=self.mail_after_date,
                on_scan_progress=lambda d, t, m, f: self.plan_scan_progress.emit(d, t, m, f),
            )

            if not self._stop_flag:
                self.plan_ready.emit(plan)

        except Exception as e:
            logger.error(f"동기화 계획 생성 오류: {e}", exc_info=True)
            if not self._stop_flag:
                self.plan_error.emit(str(e))
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
