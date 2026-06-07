"""
OutLook AnyFinder Ver0.9.1.1 for SESUNG Team
앱 진입점 (v8 — 인덱싱 항상 사용자 승인 필요)

흐름:
  1. DB 확인
  2-A. DB 비어있음 (최초) → 동의 다이얼로그 → 전체 인덱싱 (사용자 승인 포함)
  2-B. DB에 데이터 있음 → 메인 화면 바로 표시
       → 사용자가 "지금 동기화" 클릭 시에만 스마트 비교+승인+실행
  ※ 프로그램 시작 시 자동 인덱싱 절대 안 함 (항상 사용자 승인 필요)
"""

import sys
import logging
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QFont, QPalette, QColor, QIcon, QPixmap, QPainter, QAction
from PyQt6.QtCore import Qt, QTimer

from ui.theme import Colors, APP_FULL_NAME, apply_theme
from ui.main_window import MainWindow
from ui.first_run_dialog import FirstRunDialog
from ui.indexing_dialog import IndexingDialog
from ui.settings_dialog import SettingsDialog
from ui.sync_folder_dialog import SyncFolderDialog
from data.database import (
    init_db, get_db_path, get_email_count, clear_search_records, get_meta,
    set_meta, purge_mock_data,
)
from workers.indexing_worker import IndexingWorker
from utils.config import load_config, save_config

def _setup_logging():
    """콘솔/윈도우 배포본 모두에서 확인 가능한 로그 설정."""
    log_dir = Path.home() / ".outlook_anyfinder" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    handlers = [logging.StreamHandler()]
    try:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    except Exception:
        pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )
    logging.getLogger(__name__).info(f"로그 파일: {log_file}")


_setup_logging()
logger = logging.getLogger(__name__)


class AppController:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName(APP_FULL_NAME)
        self.app.setFont(QFont("Segoe UI", 10))
        self.app.setQuitOnLastWindowClosed(False)

        self.config = load_config()
        logger.info(f"Python 실행 파일: {sys.executable}")
        logger.info(f"플랫폼: {sys.platform}")
        apply_theme(self.config.get("ui", {}).get("theme", "dark"))
        self._setup_palette()

        self.db_path = get_db_path()
        self.conn = init_db(self.db_path)
        clear_search_records(self.conn)  # 실행 시 검색 기록 초기화 (북마크는 유지)
        self.use_mock = sys.platform != "win32"
        # Windows 실제 Outlook 환경에서 이전 데모/Mock 데이터가 남아 있으면
        # last_sync_time 때문에 실제 Outlook 전체 동기화가 0건으로 끝날 수 있으므로 제거한다.
        if not self.use_mock:
            removed = purge_mock_data(self.conn)
            if removed:
                logger.info(f"Mock/Demo 메일 {removed}건 삭제 — 실제 Outlook 동기화를 위해 초기화")
        self.window = None
        self.tray = None
        self.sync_plan_worker = None
        self.sync_execute_worker = None
        self.sync_dialog = None
        self.pending_sync_folder_ids = None
        self.pending_sync_include_subfolders = True
        self.pending_sync_after_date = None
        self.pending_sync_mail_after_date = None
        self.pending_sync_range_months = 0
        self.pending_sync_incremental = False
        self.background_indexing_worker = None

    def run(self):
        email_count = get_email_count(self.conn)
        logger.info(f"DB 메일 수: {email_count}건")

        if email_count == 0:
            # ═══ 케이스 A: DB 비어있음 → 최초 실행 (인덱싱 페이지 바로) ═══
            logger.info("DB 비어있음 — 최초 인덱싱 페이지 표시")
            self._do_first_run()
        else:
            # ═══ 케이스 B: DB에 데이터 있음 → 메인 화면 바로 (자동 인덱싱 없음) ═══
            logger.info(f"DB에 {email_count:,}건 존재 — 메인 화면 바로 표시")
            # ★ 자동 인덱싱/동기화 절대 하지 않음

        # 메인 윈도우 즉시 표시
        self._create_main_window()
        self._setup_tray()
        self.window.show()
        logger.info("메인 윈도우 표시 완료")

        return self.app.exec()

    def _do_first_run(self):
        """최초 실행: 동의 → 폴더 선택 → 전체 인덱싱"""
        dialog = FirstRunDialog()
        result = dialog.exec()

        if result == QDialog.DialogCode.Accepted:
            folder_ids = dialog.selected_folders or [6, 5]
            include_sub = dialog.include_subfolders
            range_months = dialog.range_months
            after_date = self._range_months_to_after_date(range_months)

            logger.info(f"사용자 수락 — 폴더: {folder_ids}, 하위폴더: {include_sub}, 범위={self._range_label(range_months)}")

            # 최초 인덱싱도 사용자가 선택한 기간 범위를 적용
            self._run_indexing(folder_ids, include_sub, is_first_run=True, after_date=after_date)
            self._refresh_conn()

            # 설정 저장
            self.config["first_run_completed"] = True
            self.config["indexing"]["folder_ids"] = folder_ids
            self.config["indexing"]["include_subfolders"] = include_sub
            self.config["indexing"]["range_months"] = range_months
            try:
                set_meta(self.conn, "indexed_range_months", str(range_months))
            except Exception:
                pass
            save_config(self.config)

            logger.info(f"최초 인덱싱 완료 — DB: {get_email_count(self.conn)}건")
        else:
            # "나중에" → Mock 데이터로 데모
            logger.info("사용자가 '나중에' 선택 — Mock 데이터로 진행")
            self._load_mock_data()

    def _run_indexing(self, folder_ids, include_sub, is_first_run, after_date=None):
        """IndexingWorker 실행 + 다이얼로그 표시"""
        dialog = IndexingDialog()
        worker = IndexingWorker(
            db_path=self.db_path, use_mock=self.use_mock,
            folder_ids=folder_ids, include_subfolders=include_sub,
            is_first_run=is_first_run,
            after_date=after_date,
        )
        worker.progress.connect(dialog.update_progress)
        worker.progress.connect(self._on_indexing_progress)
        worker.speed_update.connect(dialog.update_speed)
        worker.plan_ready.connect(dialog.on_plan_ready)
        worker.finished_indexing.connect(dialog.on_indexing_finished)
        worker.error_occurred.connect(dialog.on_indexing_error)
        dialog.on_pause_clicked = worker.pause
        dialog.on_resume_clicked = worker.resume
        dialog.on_stop_clicked = worker.stop
        # 최초 실행/인덱싱 중 '백그라운드' 선택 시 모달 창만 닫고 작업은 계속 유지
        dialog.on_background_clicked = dialog.accept
        worker.finished_indexing.connect(self._on_background_indexing_done)
        worker.error_occurred.connect(lambda e: self._on_background_indexing_error(e))
        worker.start()
        dialog.exec()
        if worker.isRunning():
            if getattr(worker, "_stop_flag", False):
                worker.wait(3000)
                return
            self.background_indexing_worker = worker
            logger.info("인덱싱을 백그라운드에서 계속 진행")
            return
        worker.wait(3000)

    def do_smart_sync_with_approval(self):
        """
        사용자가 수동으로 '동기화'를 요청했을 때만 실행.
        무거운 Outlook 스캔/비교(create_plan)는 SyncPlanWorker에서 백그라운드로 수행한다.
        """
        if self.sync_plan_worker and self.sync_plan_worker.isRunning():
            logger.info("동기화 비교가 이미 실행 중")
            return
        if self.sync_execute_worker and self.sync_execute_worker.isRunning():
            logger.info("동기화 실행이 이미 실행 중")
            return

        logger.info("사용자 요청 — 동기화 대상 폴더 선택")

        default_folder_ids = self.config.get("indexing", {}).get("folder_ids", [6, 5])
        default_include_sub = self.config.get("indexing", {}).get("include_subfolders", True)
        default_range_months = self.config.get("indexing", {}).get("range_months", 6)
        folder_dialog = SyncFolderDialog(
            selected_folders=default_folder_ids,
            include_subfolders=default_include_sub,
            range_months=default_range_months,
            parent=self.window,
        )
        if folder_dialog.exec() != QDialog.DialogCode.Accepted:
            logger.info("사용자가 동기화 대상 선택을 취소함")
            return

        folder_ids = folder_dialog.selected_folders or [6, 5]
        include_sub = folder_dialog.include_subfolders
        range_months = folder_dialog.range_months
        range_after_date = self._range_months_to_after_date(range_months)
        last_sync_time = None
        try:
            last_sync_time = get_meta(self.conn, "last_sync_time", None)
        except Exception:
            last_sync_time = None

        # 최초 동기화 이후에는 수동 동기화도 증분 스캔을 사용한다.
        # 다만 아래 경우에는 증분이 아니라 사용자가 선택한 기간 기준으로 다시 스캔한다.
        # 1) 선택한 폴더 중 DB에 아직 한 건도 없는 폴더가 있음
        # 2) 사용자가 기존 인덱싱 범위보다 더 넓은 범위(3개월→6개월/1년/전체)를 선택함
        try:
            selected_folder_counts = self._get_selected_folder_counts(folder_ids)
            selected_has_all_folders = all(cnt > 0 for cnt in selected_folder_counts.values()) if selected_folder_counts else False
            real_count = sum(selected_folder_counts.values())
        except Exception:
            selected_folder_counts = {}
            selected_has_all_folders = False
            real_count = get_email_count(self.conn)

        stored_range = self._get_indexed_range_months()
        range_expanded = self._is_range_expanded(stored_range, range_months)
        incremental = bool(last_sync_time and real_count > 0 and selected_has_all_folders and not range_expanded)
        after_date = last_sync_time if incremental else range_after_date

        self.pending_sync_folder_ids = folder_ids
        self.pending_sync_include_subfolders = include_sub
        self.pending_sync_range_months = range_months
        self.pending_sync_after_date = after_date
        self.pending_sync_mail_after_date = range_after_date if incremental else None
        self.pending_sync_incremental = incremental

        mode_text = "증분" if incremental else self._range_label(range_months)
        logger.info(f"선택 폴더 DB 건수: {selected_folder_counts}")
        logger.info(f"기존 인덱싱 범위: {self._range_label(stored_range)}, 요청 범위: {self._range_label(range_months)}, 범위확장={range_expanded}")
        logger.info(f"사용자 요청 — 백그라운드 스마트 동기화 비교 시작: 폴더={folder_ids}, 하위폴더={include_sub}, 모드={mode_text}")

        if self.window:
            names = ", ".join(SyncFolderDialog.folder_names(folder_ids))
            self._set_sync_ui_running(True, f"Outlook 확인 중... ({names} · {mode_text})")

        try:
            from workers.sync_plan_worker import SyncPlanWorker

            self.sync_plan_worker = SyncPlanWorker(
                db_path=self.db_path,
                use_mock=self.use_mock,
                folder_ids=folder_ids,
                include_subfolders=include_sub,
                after_date=after_date,
                incremental=incremental,
                mail_after_date=self.pending_sync_mail_after_date,
            )
            self.sync_plan_worker.plan_progress.connect(self._on_sync_plan_progress)
            self.sync_plan_worker.plan_scan_progress.connect(self._on_sync_plan_scan_progress)
            self.sync_plan_worker.plan_ready.connect(self._on_sync_plan_ready)
            self.sync_plan_worker.plan_error.connect(self._on_sync_plan_error)
            self.sync_plan_worker.finished.connect(self._on_sync_plan_worker_finished)
            self.sync_plan_worker.start()

        except Exception as e:
            logger.warning(f"스마트 비교 시작 실패: {e}")
            self._set_sync_ui_running(False)
            if self.window:
                self.window.sidebar.update_sync_status("동기화 확인 실패", False)
            QMessageBox.warning(
                self.window,
                "동기화 오류",
                f"Outlook 메일 비교를 시작하는 중 오류가 발생했습니다.\n\n{e}"
            )

    def _get_indexed_range_months(self) -> int:
        """현재 DB가 커버한다고 기록된 최대 인덱싱 범위.

        0은 전체를 의미한다. 메타가 없으면 아직 신뢰 가능한 범위 정보가 없는 것으로 보고 -1 반환.
        """
        try:
            value = get_meta(self.conn, "indexed_range_months", None)
            return int(value) if value is not None and str(value).strip() != "" else -1
        except Exception:
            return -1

    def _range_weight(self, months: int) -> int:
        """범위 비교용 가중치. 0(전체)은 가장 넓은 범위."""
        if months == 0:
            return 10_000
        if months is None or months < 0:
            return -1
        return int(months)

    def _is_range_expanded(self, stored_months: int, requested_months: int) -> bool:
        """요청 범위가 기존 인덱싱 커버리지보다 넓으면 True."""
        return self._range_weight(requested_months) > self._range_weight(stored_months)

    def _merged_range_months(self, stored_months: int, requested_months: int) -> int:
        """DB 커버리지 메타 저장용 최대 범위 계산."""
        if stored_months == 0 or requested_months == 0:
            return 0
        if stored_months is None or stored_months < 0:
            return requested_months
        return max(stored_months, requested_months)

    def _get_selected_folder_counts(self, folder_ids):
        """선택 폴더별 실제 Outlook 인덱싱 데이터 수를 별칭 포함해 계산."""
        from data.database import get_folder_aliases
        result = {}
        for fid in folder_ids:
            names = get_folder_aliases(fid)
            if not names:
                result[fid] = 0
                continue
            placeholders = ",".join("?" for _ in names)
            row = self.conn.execute(
                f"SELECT COUNT(*) as cnt FROM emails WHERE entry_id NOT LIKE 'MOCK_%' AND folder_name IN ({placeholders})",
                names,
            ).fetchone()
            result[fid] = row["cnt"] if row else 0
        return result

    def _range_months_to_after_date(self, months: int):
        if not months or months <= 0:
            return None
        from datetime import datetime, timedelta
        return (datetime.now() - timedelta(days=months * 30)).strftime("%Y-%m-%d %H:%M:%S")

    def _range_label(self, months: int) -> str:
        return {3: "최근 3개월", 6: "최근 6개월", 12: "최근 1년", 0: "전체"}.get(months, "전체")

    def _on_indexing_progress(self, done: int, total: int, message: str, folder: str = ""):
        if self.window:
            self.window.sidebar.update_sync_progress(done, total, message, folder)

    def _on_sync_execute_progress(self, done: int, total: int, message: str, folder: str = ""):
        if self.window:
            self.window.sidebar.update_sync_progress(done, total, message, folder)

    def _set_sync_ui_running(self, running: bool, message: str = None):
        if self.window:
            self.window.sidebar.set_sync_running(running, message)
            self.window.setWindowTitle(
                f"🔄 동기화 중 — {APP_FULL_NAME}" if running else f"📧 {APP_FULL_NAME}"
            )
        if self.tray:
            self.tray.setToolTip(f"{APP_FULL_NAME} — 동기화 중" if running else APP_FULL_NAME)

    def stop_current_sync(self):
        """사용자 요청으로 현재 동기화/비교 작업 중지."""
        stopped = False
        if self.sync_plan_worker and self.sync_plan_worker.isRunning():
            self.sync_plan_worker.stop()
            stopped = True
        if self.sync_execute_worker and self.sync_execute_worker.isRunning():
            self.sync_execute_worker.stop()
            stopped = True
        if self.background_indexing_worker and self.background_indexing_worker.isRunning():
            self.background_indexing_worker.stop()
            stopped = True
        if stopped:
            logger.info("사용자 요청 — 동기화 중지")
            self._set_sync_ui_running(True, "동기화 중지 요청 중...")
        else:
            self._set_sync_ui_running(False)

    def _on_sync_plan_progress(self, message: str):
        if self.window:
            self.window.sidebar.update_sync_progress(0, 0, message, "비교")

    def _on_sync_plan_scan_progress(self, done: int, total: int, message: str, folder: str = ""):
        if self.window:
            self.window.sidebar.update_sync_progress(done, total, message, folder or "스캔")

    def _on_sync_plan_ready(self, plan):
        folder_ids = self.pending_sync_folder_ids or self.config.get("indexing", {}).get("folder_ids", [6, 5])
        include_sub = self.pending_sync_include_subfolders
        after_date = self.pending_sync_after_date
        range_months = self.pending_sync_range_months
        incremental = self.pending_sync_incremental

        if plan.has_changes:
            detail = []
            selected_names = ", ".join(SyncFolderDialog.folder_names(folder_ids))
            detail.append(f"  📁 대상 폴더: {selected_names}")
            detail.append(f"  📂 하위 폴더: {'포함' if include_sub else '제외'}")
            detail.append(f"  🗓 모드: {'증분 동기화' if incremental else self._range_label(range_months)}")
            if plan.new_ids:
                detail.append(f"  📥 새 메일: {len(plan.new_ids)}건")
            if plan.updated_ids:
                detail.append(f"  🔄 수정된 메일: {len(plan.updated_ids)}건")
            if plan.deleted_ids:
                detail.append(f"  🗑 삭제된 메일: {len(plan.deleted_ids)}건")
            detail.append(f"  ✅ 변경 없음: {plan.skipped_count:,}건")
            detail_text = chr(10).join(detail)

            reply = self._ask_sync_approval(
                f"📧 {APP_FULL_NAME} — 메일 업데이트",
                f"Outlook 메일을 확인한 결과 변경 사항이 있습니다.\n\n"
                f"{detail_text}\n\n"
                f"지금 인덱스를 업데이트하시겠습니까?\n"
                f"(No를 선택하면 기존 데이터로 검색합니다)"
            )

            if reply == QMessageBox.StandardButton.Yes:
                self._start_sync_execute(plan, folder_ids, include_sub, after_date, range_months)
            else:
                logger.info("사용자가 업데이트 건너뜀")
                self._set_sync_ui_running(False)
                if self.window:
                    self.window.sidebar.update_sync_status(
                        f"총 {get_email_count(self.conn):,}건 인덱싱됨", True)
            return

        # 변경 없음
        logger.info(f"변경 없음 — {plan.skipped_count:,}건 최신 상태")
        self._set_sync_ui_running(False)
        if self.window:
            self.window.sidebar.update_sync_status(
                f"총 {get_email_count(self.conn):,}건 · 최신 상태", True)
        QMessageBox.information(
            self.window,
            f"📧 {APP_FULL_NAME}",
            f"모든 메일이 이미 최신 상태입니다.\n\n"
            f"✅ {plan.skipped_count:,}건 동일 (스킵)"
        )

    def _ask_sync_approval(self, title: str, text: str):
        """동기화 여부 확인창: Yes/No 버튼을 둥글고 구분하기 쉽게 표시."""
        box = QMessageBox(self.window)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Question)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.Yes)
        yes_btn = box.button(QMessageBox.StandardButton.Yes)
        no_btn = box.button(QMessageBox.StandardButton.No)
        if yes_btn:
            yes_btn.setText("Yes  동기화")
        if no_btn:
            no_btn.setText("No  건너뛰기")
        box.setStyleSheet(f"""
            QMessageBox {{
                background-color: {Colors.BG_MAIN};
                color: {Colors.TEXT_PRIMARY};
            }}
            QMessageBox QLabel {{
                color: {Colors.TEXT_PRIMARY};
                background: transparent;
                font-size: 13px;
            }}
            QMessageBox QPushButton {{
                min-width: 150px;
                min-height: 38px;
                padding: 8px 24px;
                border-radius: 10px;
                font-weight: 700;
                border: 2px solid {Colors.BORDER_LIGHT};
                background: {Colors.BG_CARD};
                color: {Colors.TEXT_SECONDARY};
            }}
            QMessageBox QPushButton:hover {{
                border: 2px solid {Colors.PRIMARY};
                background: {Colors.BG_CARD_HOVER};
                color: {Colors.TEXT_PRIMARY};
            }}
            QMessageBox QPushButton:default {{
                background: {Colors.PRIMARY};
                color: #FFFFFF;
                border: 2px solid {Colors.PRIMARY};
            }}
            QMessageBox QPushButton:default:hover {{
                background: {Colors.PRIMARY_HOVER};
                color: #FFFFFF;
                border: 2px solid {Colors.BORDER_FOCUS};
            }}
        """)
        return box.exec()

    def _on_sync_plan_error(self, error: str):
        logger.warning(f"스마트 비교 실패: {error}")
        self._set_sync_ui_running(False)
        if self.window:
            self.window.sidebar.update_sync_status("동기화 확인 실패", False)
        QMessageBox.warning(
            self.window,
            "동기화 오류",
            f"Outlook 메일 비교 중 오류가 발생했습니다.\n\n{error}"
        )

    def _on_sync_plan_worker_finished(self):
        if self.sync_plan_worker:
            self.sync_plan_worker.deleteLater()
        self.sync_plan_worker = None
        if not (self.sync_execute_worker and self.sync_execute_worker.isRunning()):
            # 중지 요청 등으로 plan_ready 없이 끝난 경우 버튼 복구
            if self.window and self.window.windowTitle().startswith("🔄"):
                self._set_sync_ui_running(False)
                self.window.sidebar.update_sync_status("동기화가 중지되었습니다", False)

    def _start_sync_execute(self, plan, folder_ids, include_sub, after_date=None, range_months=0):
        """승인된 동기화 계획을 비모달 진행창 + 백그라운드 워커로 실행."""
        if self.sync_execute_worker and self.sync_execute_worker.isRunning():
            return

        from workers.sync_execute_worker import SyncExecuteWorker

        self.sync_dialog = IndexingDialog(parent=self.window)
        self.sync_dialog.setWindowTitle(f"{APP_FULL_NAME} — 동기화")
        selected_names = ", ".join(SyncFolderDialog.folder_names(folder_ids))
        self.sync_dialog.title_label.setText("📧 선택한 폴더 동기화 진행 중...")
        mode_text = "증분 동기화" if self.pending_sync_incremental else self._range_label(range_months)
        self.sync_dialog.on_plan_ready(
            f"대상 폴더: {selected_names}\n하위 폴더: {'포함' if include_sub else '제외'}\n모드: {mode_text}\n{plan.changes_summary}",
            plan.has_changes,
        )

        self.sync_execute_worker = SyncExecuteWorker(
            db_path=self.db_path,
            use_mock=self.use_mock,
            plan=plan,
            folder_ids=folder_ids,
            include_subfolders=include_sub,
            after_date=after_date,
            incremental=self.pending_sync_incremental,
        )

        self.sync_execute_worker.progress.connect(self.sync_dialog.update_progress)
        self.sync_execute_worker.progress.connect(self._on_sync_execute_progress)
        self.sync_execute_worker.speed_update.connect(self.sync_dialog.update_speed)
        self.sync_execute_worker.finished_sync.connect(self.sync_dialog.on_indexing_finished)
        self.sync_execute_worker.finished_sync.connect(self._on_sync_execute_done)
        self.sync_execute_worker.error_occurred.connect(self.sync_dialog.on_indexing_error)
        self.sync_execute_worker.error_occurred.connect(self._on_sync_execute_error)
        self.sync_execute_worker.finished.connect(self._on_sync_execute_worker_finished)
        self.sync_dialog.finished.connect(self._on_sync_dialog_finished)

        self.sync_dialog.on_stop_clicked = self.sync_execute_worker.stop
        self.sync_dialog.on_background_clicked = self.sync_dialog.hide

        self._set_sync_ui_running(True, "동기화 중...")

        self.sync_execute_worker.start()
        self.sync_dialog.show()  # 비모달: 동기화 중에도 메인 화면 사용 가능

    def _on_sync_execute_done(self, stats: dict):
        self._refresh_conn()
        try:
            stored = self._get_indexed_range_months()
            merged = self._merged_range_months(stored, self.pending_sync_range_months)
            set_meta(self.conn, "indexed_range_months", str(merged))
        except Exception:
            pass
        self._set_sync_ui_running(False)
        if self.window:
            self.window.reset_db_connection(self.conn, show_all_if_no_query=True)
            self.window.sidebar.update_sync_status(stats.get("message", "동기화 완료"), True)

    def _on_sync_execute_error(self, error: str):
        self._set_sync_ui_running(False)
        if self.window:
            self.window.sidebar.update_sync_status(f"오류: {error}", False)

    def _on_sync_execute_worker_finished(self):
        was_running_title = bool(self.window and self.window.windowTitle().startswith("🔄"))
        if self.sync_execute_worker:
            self.sync_execute_worker.deleteLater()
        self.sync_execute_worker = None
        if was_running_title:
            self._set_sync_ui_running(False)
            if self.window:
                self.window.sidebar.update_sync_status("동기화가 중지되었습니다", False)

    def _on_sync_dialog_finished(self):
        if self.sync_dialog:
            self.sync_dialog.deleteLater()
        self.sync_dialog = None

    def _on_background_indexing_done(self, stats: dict):
        try:
            self._refresh_conn()
            if self.window:
                self.window.reset_db_connection(self.conn, show_all_if_no_query=True)
                self.window.sidebar.update_sync_status(stats.get("message", "동기화 완료"), True)
                self.window.sidebar.set_sync_running(False)
                self.window.setWindowTitle(f"📧 {APP_FULL_NAME}")
            if self.tray:
                self.tray.setToolTip(APP_FULL_NAME)
        finally:
            if self.background_indexing_worker:
                self.background_indexing_worker.deleteLater()
            self.background_indexing_worker = None

    def _on_background_indexing_error(self, error: str):
        if self.window:
            self.window.sidebar.update_sync_status(f"오류: {error}", False)
            self.window.sidebar.set_sync_running(False)
            self.window.setWindowTitle(f"📧 {APP_FULL_NAME}")
        if self.tray:
            self.tray.setToolTip(APP_FULL_NAME)

    def _load_mock_data(self):
        from core.index_builder import IndexBuilder
        from core.outlook_connector import MockOutlookConnector, OlDefaultFolders
        c = MockOutlookConnector(); c.connect()
        b = IndexBuilder(self.conn)
        m = list(c.iter_mails(OlDefaultFolders.INBOX)) + list(c.iter_mails(OlDefaultFolders.SENT))
        b.build_from_iterator(iter(m), len(m))

    def _refresh_conn(self):
        try: self.conn.close()
        except: pass
        self.conn = init_db(self.db_path)

    def _create_main_window(self):
        self.window = MainWindow(self.conn, self.db_path, self.use_mock)
        self.window.sidebar.settings_clicked.connect(self._open_settings)
        # ★ 사이드바 "지금 동기화" → 사용자 승인 동기화로 연결
        self.window.sidebar.sync_requested.disconnect()  # 기존 연결 해제
        self.window.sidebar.sync_requested.connect(self.do_smart_sync_with_approval)
        self.window.sidebar.sync_stop_requested.connect(self.stop_current_sync)
        self.window.set_tray_mode(True)
        if self.background_indexing_worker and self.background_indexing_worker.isRunning():
            self.window.sidebar.set_sync_running(True, "백그라운드 동기화 중...")
            self.window.setWindowTitle(f"🔄 동기화 중 — {APP_FULL_NAME}")

    # ═══ 트레이 ═══

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable(): return
        px = QPixmap(32, 32); px.fill(QColor("transparent"))
        p = QPainter(px); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(Colors.PRIMARY)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(2,2,28,28,6,6); p.setPen(QColor("#FFF"))
        p.setFont(QFont("Segoe UI",14,QFont.Weight.Bold))
        p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "M"); p.end()

        self.tray = QSystemTrayIcon(QIcon(px), self.app)
        self.tray.setToolTip(APP_FULL_NAME)
        if self.background_indexing_worker and self.background_indexing_worker.isRunning():
            self.tray.setToolTip(f"{APP_FULL_NAME} — 동기화 중")
        menu = QMenu()
        menu.setStyleSheet(f"QMenu{{background:{Colors.BG_ELEVATED};color:{Colors.TEXT_PRIMARY};border:1px solid {Colors.BORDER_LIGHT};border-radius:8px;padding:4px;}}QMenu::item{{padding:6px 20px;border-radius:4px;}}QMenu::item:selected{{background:{Colors.PRIMARY};color:#FFF;}}")

        show_act = QAction("📧 열기", menu)
        show_act.triggered.connect(self._show)
        menu.addAction(show_act)

        # ★ 트레이 동기화도 사용자 승인 방식
        sync_act = QAction("🔄 동기화", menu)
        sync_act.triggered.connect(self.do_smart_sync_with_approval)
        menu.addAction(sync_act)

        menu.addSeparator()
        quit_act = QAction("❌ 종료", menu)
        quit_act.triggered.connect(self._quit)
        menu.addAction(quit_act)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self._show() if r == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()

    def _show(self):
        if self.window: self.window.showNormal(); self.window.raise_(); self.window.activateWindow()

    def _quit(self):
        if self.window: self.window.set_tray_mode(False); self.window.close()
        if self.tray: self.tray.hide()
        self.app.quit()

    def _open_settings(self):
        d = SettingsDialog(db_conn=self.conn, parent=self.window)
        d.settings_saved.connect(self._on_settings_saved)
        d.data_reset.connect(self._on_data_reset)
        d.exec()

    def _on_data_reset(self):
        """설정에서 전체 데이터 초기화 후 메인 화면/폴더 카운트 즉시 초기화."""
        self._refresh_conn()
        if self.window:
            self.window.reset_db_connection(self.conn, refresh_current_view=False)
            self.window.search_bar.search_input.clear()
            self.window.result_list.clear_results("데이터가 초기화되었습니다. 동기화를 다시 시작해 주세요.")
            self.window.mail_preview.clear()
            self.window.sidebar.update_sync_status("데이터 초기화 완료", True)

    def _on_settings_saved(self, new_config: dict):
        old_theme = self.config.get("ui", {}).get("theme", "dark")
        new_theme = new_config.get("ui", {}).get("theme", "dark")
        self.config = new_config

        if old_theme != new_theme:
            apply_theme(new_theme)
            self._setup_palette()
            self._recreate_main_window()
        elif self.window:
            self.window.apply_new_settings(new_config)

    def _recreate_main_window(self):
        """테마 변경 시 새 테마 스타일로 메인 윈도우를 재생성한다."""
        was_visible = bool(self.window and self.window.isVisible())
        if self.window:
            try:
                self.window.set_tray_mode(False)
                self.window.close()
                self.window.deleteLater()
            except Exception:
                pass
            self.window = None
        self._create_main_window()
        if was_visible or self.window:
            self.window.show()

    def _setup_palette(self):
        p = QPalette()
        for r, c in [(QPalette.ColorRole.Window, Colors.BG_MAIN),(QPalette.ColorRole.WindowText, Colors.TEXT_PRIMARY),
                      (QPalette.ColorRole.Base, Colors.BG_INPUT),(QPalette.ColorRole.Text, Colors.TEXT_PRIMARY),
                      (QPalette.ColorRole.Button, Colors.BG_CARD),(QPalette.ColorRole.ButtonText, Colors.TEXT_PRIMARY),
                      (QPalette.ColorRole.Highlight, Colors.PRIMARY)]:
            p.setColor(r, QColor(c))
        self.app.setPalette(p)


def main():
    sys.exit(AppController().run())

if __name__ == "__main__":
    main()
