"""
OutLook AnyFinder Ver0.9.1.1 for SESUNG Team
[W01] 인덱싱 QThread (v3 — 스레드 안전: DB+COM 모두 스레드 내 생성)
"""

import logging
import time
from typing import List

from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QWaitCondition

logger = logging.getLogger(__name__)


class IndexingWorker(QThread):
    progress = pyqtSignal(int, int, str, str)
    speed_update = pyqtSignal(float)
    plan_ready = pyqtSignal(str, bool)
    finished_indexing = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    status_changed = pyqtSignal(str)

    def __init__(self, db_path, use_mock: bool, folder_ids: List[int] = None,
                 include_subfolders: bool = True, is_first_run: bool = False,
                 after_date=None, parent=None):
        super().__init__(parent)
        self.db_path = db_path          # DB 경로 (스레드 내에서 새 연결 생성)
        self.use_mock = use_mock        # Mock 여부
        self.folder_ids = folder_ids or [6, 5]
        self.include_subfolders = include_subfolders
        self.is_first_run = is_first_run
        self.after_date = after_date

        self._stop_flag = False
        self._paused = False
        self._mutex = QMutex()
        self._pause_condition = QWaitCondition()

    def pause(self):
        self._mutex.lock()
        self._paused = True
        self._mutex.unlock()
        self.status_changed.emit("paused")

    def resume(self):
        self._mutex.lock()
        self._paused = False
        self._mutex.unlock()
        self._pause_condition.wakeAll()
        self.status_changed.emit("running")

    def stop(self):
        self._stop_flag = True
        if self._paused:
            self.resume()
        self.status_changed.emit("stopped")

    def run(self):
        """스레드 내에서 DB 연결 + COM 연결을 새로 생성"""
        conn = None
        connector = None
        try:
            self.status_changed.emit("running")

            # ★ 스레드 내에서 새 DB 연결 생성
            from data.database import init_db
            conn = init_db(self.db_path)

            # ★ 스레드 내에서 새 Outlook COM 연결 생성
            from core.outlook_connector import create_connector
            connector = create_connector(use_mock=self.use_mock)
            connector.connect()

            if self.is_first_run:
                self._do_full_indexing(conn, connector)
            else:
                self._do_smart_sync(conn, connector)

            conn.close()
            conn = None

        except Exception as e:
            error_msg = f"인덱싱 오류: {e}"
            logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
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

    def _do_smart_sync(self, conn, connector):
        from core.sync_manager import SyncManager, MockSyncManager
        from core.outlook_connector import MockOutlookConnector

        if isinstance(connector, MockOutlookConnector):
            sm = MockSyncManager(conn, connector)
        else:
            sm = SyncManager(conn, connector)

        self.progress.emit(0, 0, "메일 목록 비교 중...", "")

        plan = sm.create_plan(
            folder_ids=self.folder_ids,
            include_subfolders=self.include_subfolders,
            on_status=lambda msg: self.progress.emit(0, 0, msg, ""),
        )

        self.plan_ready.emit(plan.changes_summary, plan.has_changes)

        if not plan.has_changes:
            self.finished_indexing.emit({
                "added": 0, "updated": 0, "deleted": 0,
                "skipped": plan.skipped_count, "errors": 0,
                "elapsed_sec": 0,
                "message": f"변경 없음 — {plan.skipped_count:,}건 최신 상태"
            })
            return

        total_work = len(plan.new_ids) + len(plan.updated_ids) + len(plan.deleted_ids)
        speed_window = []

        def on_progress(done, total, message):
            self.progress.emit(done, total_work, message, "")
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
            plan, folder_ids=self.folder_ids,
            include_subfolders=self.include_subfolders,
            on_progress=on_progress,
            should_stop=lambda: self._stop_flag,
        )

        self.finished_indexing.emit({
            "added": result.added, "updated": result.updated,
            "deleted": result.deleted, "skipped": result.skipped,
            "errors": result.errors, "elapsed_sec": result.elapsed_sec,
            "message": result.summary,
        })

    def _do_full_indexing(self, conn, connector):
        from core.index_builder import IndexBuilder
        from core.outlook_connector import OlDefaultFolders

        builder = IndexBuilder(conn)

        total_count = 0
        try:
            total_count = connector.get_total_mail_count(
                folder_ids=self.folder_ids,
                include_subfolders=self.include_subfolders,
                after_date=self.after_date,
                incremental=False,
            )
        except Exception:
            pass

        self.progress.emit(0, total_count, "시작 중...", "")

        overall = {"added": 0, "skipped": 0, "errors": 0, "elapsed_sec": 0}
        start = time.time()
        speed_window = []
        overall_done = 0

        for fid in self.folder_ids:
            if self._stop_flag:
                break

            fname = OlDefaultFolders.NAMES.get(fid, f"폴더{fid}")

            try:
                mail_iter = connector.iter_mails(
                    fid,
                    include_subfolders=self.include_subfolders,
                    after_date=self.after_date,
                    incremental=False,
                )

                def on_progress(done, total, subject):
                    nonlocal overall_done
                    overall_done = overall["added"] + overall["skipped"] + overall["errors"] + done
                    self.progress.emit(overall_done, total_count, subject, fname)

                    now = time.time()
                    speed_window.append((now, overall_done))
                    while speed_window and now - speed_window[0][0] > 3.0:
                        speed_window.pop(0)
                    if len(speed_window) >= 2:
                        dt = speed_window[-1][0] - speed_window[0][0]
                        dc = speed_window[-1][1] - speed_window[0][1]
                        if dt > 0:
                            self.speed_update.emit(dc / dt)

                stats = builder.build_from_iterator(
                    mail_iterator=mail_iter,
                    total_count=total_count,
                    on_progress=on_progress,
                    should_stop=lambda: self._stop_flag,
                    is_paused=lambda: self._paused,
                )

                overall["added"] += stats["indexed"]
                overall["skipped"] += stats["skipped"]
                overall["errors"] += stats["errors"]

            except Exception as e:
                logger.error(f"폴더 '{fname}' 인덱싱 오류: {e}")
                overall["errors"] += 1

        overall["elapsed_sec"] = round(time.time() - start, 2)

        if not self._stop_flag:
            try:
                builder.optimize_fts_index()
            except Exception:
                pass

        overall["message"] = f"{overall['added']}건 추가, {overall['skipped']}건 스킵, {overall['elapsed_sec']}초"
        self.finished_indexing.emit(overall)
