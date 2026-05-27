"""
OutLook AnyFinder Ver0.9 for SESUNG Team
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

from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QFont, QPalette, QColor, QIcon, QPixmap, QPainter, QAction
from PyQt6.QtCore import Qt, QTimer

from ui.theme import Colors, APP_FULL_NAME
from ui.main_window import MainWindow
from ui.first_run_dialog import FirstRunDialog
from ui.indexing_dialog import IndexingDialog
from ui.settings_dialog import SettingsDialog
from data.database import init_db, get_db_path, get_email_count
from workers.indexing_worker import IndexingWorker
from utils.config import load_config, save_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)


class AppController:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName(APP_FULL_NAME)
        self.app.setFont(QFont("Segoe UI", 10))
        self.app.setQuitOnLastWindowClosed(False)
        self._setup_palette()

        self.db_path = get_db_path()
        self.conn = init_db(self.db_path)
        self.config = load_config()
        self.use_mock = sys.platform != "win32"
        self.window = None
        self.tray = None

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

            logger.info(f"사용자 수락 — 폴더: {folder_ids}, 하위폴더: {include_sub}")

            # 전체 인덱싱
            self._run_indexing(folder_ids, include_sub, is_first_run=True)
            self._refresh_conn()

            # 설정 저장
            self.config["first_run_completed"] = True
            self.config["indexing"]["folder_ids"] = folder_ids
            self.config["indexing"]["include_subfolders"] = include_sub
            save_config(self.config)

            logger.info(f"최초 인덱싱 완료 — DB: {get_email_count(self.conn)}건")
        else:
            # "나중에" → Mock 데이터로 데모
            logger.info("사용자가 '나중에' 선택 — Mock 데이터로 진행")
            self._load_mock_data()

    def _run_indexing(self, folder_ids, include_sub, is_first_run):
        """IndexingWorker 실행 + 다이얼로그 표시"""
        dialog = IndexingDialog()
        worker = IndexingWorker(
            db_path=self.db_path, use_mock=self.use_mock,
            folder_ids=folder_ids, include_subfolders=include_sub,
            is_first_run=is_first_run,
        )
        worker.progress.connect(dialog.update_progress)
        worker.speed_update.connect(dialog.update_speed)
        worker.plan_ready.connect(dialog.on_plan_ready)
        worker.finished_indexing.connect(dialog.on_indexing_finished)
        worker.error_occurred.connect(dialog.on_indexing_error)
        dialog.on_pause_clicked = worker.pause
        dialog.on_resume_clicked = worker.resume
        dialog.on_stop_clicked = worker.stop
        worker.start()
        dialog.exec()
        worker.wait(10000)

    def do_smart_sync_with_approval(self):
        """
        ★ 사용자가 수동으로 '동기화'를 요청했을 때만 실행.
        스마트 비교 → 결과 표시 → 사용자 승인 → 실행
        """
        logger.info("사용자 요청 — 스마트 동기화 시작")

        if self.window:
            self.window.sidebar.update_sync_status("Outlook 확인 중...", True)

        try:
            from core.sync_manager import SyncManager, MockSyncManager
            from core.outlook_connector import create_connector, MockOutlookConnector

            folder_ids = self.config.get("indexing", {}).get("folder_ids", [6, 5])
            include_sub = self.config.get("indexing", {}).get("include_subfolders", True)

            connector = create_connector(use_mock=self.use_mock)
            connector.connect()

            if isinstance(connector, MockOutlookConnector):
                sm = MockSyncManager(self.conn, connector)
            else:
                sm = SyncManager(self.conn, connector)

            plan = sm.create_plan(folder_ids=folder_ids, include_subfolders=include_sub)

            if plan.has_changes:
                # ★ 변경 있음 → 사용자 승인 요청
                detail = []
                if plan.new_ids:
                    detail.append(f"  📥 새 메일: {len(plan.new_ids)}건")
                if plan.updated_ids:
                    detail.append(f"  🔄 수정된 메일: {len(plan.updated_ids)}건")
                if plan.deleted_ids:
                    detail.append(f"  🗑 삭제된 메일: {len(plan.deleted_ids)}건")
                detail.append(f"  ✅ 변경 없음: {plan.skipped_count:,}건")
                detail_text = chr(10).join(detail)

                reply = QMessageBox.question(
                    self.window,
                    f"📧 {APP_FULL_NAME} — 메일 업데이트",
                    f"Outlook 메일을 확인한 결과 변경 사항이 있습니다.\n\n"
                    f"{detail_text}\n\n"
                    f"지금 인덱스를 업데이트하시겠습니까?\n"
                    f"(아니오를 선택하면 기존 데이터로 검색합니다)",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )

                if reply == QMessageBox.StandardButton.Yes:
                    self._run_indexing(folder_ids, include_sub, is_first_run=False)
                    self._refresh_conn()
                    if self.window:
                        self.window.conn = self.conn
                        self.window._initial_load()
                else:
                    logger.info("사용자가 업데이트 건너뜀")

                if self.window:
                    self.window.sidebar.update_sync_status(
                        f"총 {get_email_count(self.conn):,}건 인덱싱됨", True)
            else:
                # ★ 변경 없음 → 알림
                logger.info(f"변경 없음 — {plan.skipped_count:,}건 최신 상태")
                if self.window:
                    self.window.sidebar.update_sync_status(
                        f"총 {get_email_count(self.conn):,}건 · 최신 상태", True)
                QMessageBox.information(
                    self.window,
                    f"📧 {APP_FULL_NAME}",
                    f"모든 메일이 이미 최신 상태입니다.\n\n"
                    f"✅ {plan.skipped_count:,}건 동일 (스킵)"
                )

        except Exception as e:
            logger.warning(f"스마트 비교 실패: {e}")
            if self.window:
                self.window.sidebar.update_sync_status("동기화 확인 실패", False)
            QMessageBox.warning(
                self.window,
                "동기화 오류",
                f"Outlook 메일 비교 중 오류가 발생했습니다.\n\n{e}"
            )

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
        self.window.set_tray_mode(True)

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
        d.settings_saved.connect(lambda c: (setattr(self, 'config', c), self.window.apply_new_settings(c) if self.window else None))
        d.exec()

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
