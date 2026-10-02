"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[U01] 메인 윈도우 (v4 — 설정 반영 + 동기화 모드 토글 + 세션 정리)
"""

import json
import logging
import time

from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut

from ui.theme import Colors, APP_FULL_NAME, global_stylesheet
from ui.sidebar import Sidebar
from ui.search_bar import SearchBar
from ui.filter_bar import FilterBar
from ui.result_list import ResultList
from ui.mail_preview import MailPreview
from core.search_engine import SearchEngine
from core.bookmark_manager import BookmarkManager
from data.database import cleanup_session_logs
from utils.date_utils import get_date_filter_range
from utils.config import load_config, save_config

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):

    def __init__(self, db_conn, db_path=None, use_mock=False):
        super().__init__()
        self.setWindowTitle(f"📧 {APP_FULL_NAME}")
        self.setMinimumSize(1100, 700)
        self.resize(1360, 820)

        self.conn = db_conn
        self.db_path = db_path
        self.use_mock = use_mock
        self.config = load_config()

        self.engine = SearchEngine(db_conn)
        self.bookmarks = BookmarkManager(db_conn)

        self._current_query = ""
        self._current_page = 1
        self._sync_worker = None

        # 시작 시 세션 로그 정리
        try:
            cleanup_session_logs(db_conn, max_rows=1000)
        except Exception:
            pass

        self._build_ui()
        self._connect_signals()
        self._load_email_suggestions()
        self._setup_auto_sync()
        self._apply_global_style()
        self._initial_load()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        ml = QHBoxLayout(central)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        self.sidebar = Sidebar()
        ml.addWidget(self.sidebar)

        content = QWidget()
        content.setStyleSheet(f"background-color:{Colors.BG_MAIN};")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(18, 14, 18, 14)
        cl.setSpacing(8)

        self.search_bar = SearchBar()
        cl.addWidget(self.search_bar)

        self.filter_bar = FilterBar()
        cl.addWidget(self.filter_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(f"QSplitter::handle{{background:{Colors.BORDER};width:1px;margin:0 6px;}}")
        self.result_list = ResultList()
        splitter.addWidget(self.result_list)
        self.mail_preview = MailPreview()
        splitter.addWidget(self.mail_preview)
        splitter.setSizes([460, 520])
        cl.addWidget(splitter, 1)
        ml.addWidget(content, 1)

    def _connect_signals(self):
        self.search_bar.search_triggered.connect(self._on_search)
        self.search_bar.bookmark_clicked.connect(self._on_bookmark_toggle)
        self.filter_bar.filter_changed.connect(self._on_filter_changed)
        self.filter_bar.sort_changed.connect(self._on_sort_changed)
        self.result_list.mail_selected.connect(self._on_mail_selected)
        self.result_list.page_requested.connect(self._on_page_requested)
        self.mail_preview.open_in_outlook.connect(self._on_open_in_outlook)
        self.sidebar.folder_selected.connect(self._on_folder_selected)
        self.sidebar.sync_requested.connect(self._on_sync_requested)
        self.sidebar.bookmark_selected.connect(self._on_bookmark_selected)

        QShortcut(QKeySequence("Ctrl+K"), self).activated.connect(self._focus_search)
        QShortcut(QKeySequence("Ctrl+J"), self).activated.connect(self._select_next)
        QShortcut(QKeySequence("Ctrl+Shift+J"), self).activated.connect(self._select_prev)
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._on_escape)

    def _load_email_suggestions(self):
        """DB에서 메일 주소 후보를 로드해 검색창 인라인 자동완성에 반영."""
        import re
        emails = set()
        try:
            rows = self.conn.execute("""
                SELECT sender_email, recipients, cc
                FROM emails
                WHERE sender_email != '' OR recipients != '' OR cc != ''
            """).fetchall()
            pattern = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
            for row in rows:
                for col in ("sender_email", "recipients", "cc"):
                    value = row[col] or ""
                    for email in pattern.findall(value):
                        emails.add(email)
            self.search_bar.set_email_suggestions(emails)
        except Exception as e:
            logger.debug(f"메일 주소 자동완성 후보 로드 실패: {e}")

    def _setup_auto_sync(self):
        """자동 동기화 타이머 + 남은 시간 표시 타이머."""
        self._sync_timer = QTimer()
        self._sync_timer.setSingleShot(False)
        self._sync_countdown_timer = QTimer()
        self._sync_countdown_timer.setInterval(1000)
        self._sync_countdown_timer.timeout.connect(self._update_auto_sync_countdown)
        self._next_auto_sync_ts = 0
        self._apply_sync_settings()

    def _apply_sync_settings(self):
        """현재 설정에 맞춰 자동 동기화 타이머 재설정."""
        self._sync_timer.stop()
        try:
            self._sync_timer.timeout.disconnect()
        except Exception:
            pass

        auto = self.config.get("sync", {}).get("auto_sync", False)
        interval = self.config.get("sync", {}).get("interval_minutes", 0)

        if auto and interval > 0:
            secs = interval * 60
            self._sync_timer.setInterval(secs * 1000)
            self._sync_timer.timeout.connect(self._on_auto_sync)
            self._sync_timer.start()
            self._next_auto_sync_ts = time.time() + secs
            self._sync_countdown_timer.start()
            self._update_auto_sync_countdown()
            logger.info(f"자동 동기화 활성화 — {interval}분 주기")
        else:
            self._next_auto_sync_ts = 0
            self._sync_countdown_timer.stop()
            self.sidebar.update_sync_status("수동 동기화", True)
            logger.info("자동 동기화 비활성화 — 수동 동기화")

    def apply_new_settings(self, new_config: dict):
        self.config = new_config
        self._apply_sync_settings()
        logger.info("설정 반영 완료")

    def reset_db_connection(self, db_conn, refresh_current_view: bool = True,
                            show_all_if_no_query: bool = False):
        """워커가 DB를 갱신한 뒤 메인 스레드의 DB 기반 객체를 재생성한다.

        - 앱 최초 실행/데이터 초기화 직후에는 이전 리스트를 자동 표시하지 않는다.
        - 동기화 완료 직후에는 show_all_if_no_query=True로 호출하여, 검색어가 없더라도
          최신 인덱싱 메일 전체 리스트와 폴더 카운트를 사용자에게 보여준다.
        """
        self.conn = db_conn
        self.engine = SearchEngine(db_conn)
        self.bookmarks = BookmarkManager(db_conn)
        self.filter_bar.load_extensions_from_db(self.conn)
        self._update_sidebar()
        self._refresh_bookmarks()
        self._load_email_suggestions()
        if refresh_current_view:
            if self._current_query.strip():
                self._execute_search(self._current_query)
            elif show_all_if_no_query:
                self._current_page = 1
                self._execute_search("", default_sort="received_at_desc")

    def _apply_global_style(self):
        self.setStyleSheet(global_stylesheet())

    def _initial_load(self):
        self.filter_bar.load_extensions_from_db(self.conn)
        self.search_bar.search_input.clear()
        self._current_query = ""
        self._current_page = 1
        self.result_list.clear_results()
        self.mail_preview.clear()
        self._update_sidebar()
        self._refresh_bookmarks()

    # ═══ 검색 ═══

    def _on_search(self, query):
        self._current_query = query
        self._current_page = 1
        self._execute_search(query)
        self.search_bar.set_bookmark_active(self.bookmarks.is_bookmarked(query) if query else False)

    def _on_filter_changed(self):
        self._current_page = 1
        self._execute_search(self._current_query)

    def _on_sort_changed(self, _):
        self._current_page = 1
        self._execute_search(self._current_query)

    def _on_page_requested(self, page: int):
        self._current_page = page
        self._execute_search(self._current_query)

    def _on_folder_selected(self, folder_name):
        self.search_bar.search_input.setText("")
        self._current_query = ""
        self.filter_bar.reset_all()
        self._execute_search("", extra_filters=[self._folder_where(folder_name)])

    def _execute_search(self, query, extra_filters=None, default_sort=None):
        sort = default_sort or self.filter_bar.get_sort_mode()
        where = self._build_where(extra_filters)
        try:
            resp = self.engine.search(
                query=query, page=self._current_page, per_page=20,
                sort_by=sort, extra_where=where,
                contains_search=self.search_bar.is_contains_search_enabled(),
            )
            self.result_list.set_results(resp.results, query)  # 하이라이트는 원본 쿼리
            self.result_list.set_pagination(resp.page, resp.total_pages, resp.total_count)
            total_db = self.engine.get_total_count()
            self.filter_bar.set_result_count(total_db, resp.total_count, resp.elapsed_ms, "FTS5" if query else "전체")
        except Exception as e:
            logger.error(f"검색 오류: {e}")

    def _folder_where(self, folder_name: str):
        """Outlook 환경별 폴더명 차이를 흡수하는 WHERE 조건."""
        aliases = {
            "받은편지함": ["받은편지함", "받은 편지함", "Inbox"],
            "보낸편지함": ["보낸편지함", "보낸 편지함", "Sent Items", "Sent"],
            "임시보관함": ["임시보관함", "임시 보관함", "Drafts"],
            "지운편지함": ["지운편지함", "지운 편지함", "Deleted Items", "Trash"],
        }
        names = aliases.get(folder_name, [folder_name])
        placeholders = ",".join("?" for _ in names)
        return (f"folder_name IN ({placeholders})", names)

    def _build_where(self, extra=None):
        w = extra or []
        a = self.filter_bar.get_active_filters()
        if a.get("inbox"): w.append(self._folder_where("받은편지함"))
        if a.get("sent"): w.append(self._folder_where("보낸편지함"))
        # has_att는 DynamicAttachmentFilter에서 처리
        att = self.filter_bar.get_attachment_filter()
        if att == "has":
            w.append(("has_attachments = ?", [1]))
        elif att == "none":
            w.append(("has_attachments = ?", [0]))
        elif att:
            w.append(("attachment_types LIKE ?", [f"%{att}%"]))
        df = self.filter_bar.get_date_filter()
        s, e = get_date_filter_range(df)
        if s: w.append(("received_at >= ?", [s]))
        if e: w.append(("received_at <= ?", [e]))
        return w if w else None

    # ═══ 북마크 ═══

    def _on_bookmark_toggle(self, query):
        if not query.strip(): return
        fs = self.filter_bar.get_filter_state()
        added = self.bookmarks.toggle(query, fs)
        self.search_bar.set_bookmark_active(added)
        self._refresh_bookmarks()

    def _on_bookmark_selected(self, bid):
        bm = self.bookmarks.get_by_id(bid)
        if bm:
            self.search_bar.search_input.setText(bm.query)
            try:
                state = json.loads(bm.filters) if bm.filters else {}
                self.filter_bar.restore_filter_state(state)
            except: pass
            self._on_search(bm.query)

    def _refresh_bookmarks(self):
        self.sidebar.update_bookmarks(self.bookmarks.get_all())

    # ═══ 동기화 ═══

    def _on_sync_requested(self):
        self._run_sync()

    def _on_auto_sync(self):
        logger.info("자동 동기화 실행")
        if getattr(self.sidebar, "_sync_running", False):
            # 수동 동기화/다른 동기화 중이면 1분 뒤 다시 시도
            self._next_auto_sync_ts = time.time() + 60
            self._update_auto_sync_countdown()
            logger.info("동기화 작업 중 — 자동 동기화 1분 연기")
            return
        interval = self.config.get("sync", {}).get("interval_minutes", 0)
        if interval > 0:
            self._next_auto_sync_ts = time.time() + interval * 60
        self._run_sync(auto=True)

    def _update_auto_sync_countdown(self):
        if not self._next_auto_sync_ts or getattr(self.sidebar, "_sync_running", False):
            return
        remain = max(0, int(self._next_auto_sync_ts - time.time()))
        mm, ss = divmod(remain, 60)
        self.sidebar.update_sync_status(f"자동동기화 {mm:02d}분{ss:02d}초", True)

    def _run_sync(self, auto=False):
        from workers.sync_worker import SyncWorker
        if self._sync_worker and self._sync_worker.isRunning():
            return
        if getattr(self.sidebar, "_sync_running", False):
            return
        self.sidebar.set_sync_running(True, "자동 동기화 중..." if auto else "동기화 중...")
        fids = self.config.get("indexing", {}).get("folder_ids", [6, 5])
        inc = self.config.get("indexing", {}).get("include_subfolders", True)
        after_date = None
        incremental = bool(auto)
        if auto:
            try:
                from data.database import get_meta
                after_date = get_meta(self.conn, "last_sync_time", None)
            except Exception:
                after_date = None
        self._sync_worker = SyncWorker(
            db_path=self.db_path, use_mock=self.use_mock,
            folder_ids=fids, include_subfolders=inc,
            after_date=after_date, incremental=incremental,
        )
        self._sync_worker.sync_progress.connect(lambda d, t, m: self.sidebar.update_sync_progress(d, t, m, "자동" if auto else ""))
        self._sync_worker.sync_finished.connect(self._on_sync_done)
        self._sync_worker.sync_error.connect(self._on_sync_error)
        self._sync_worker.start()

    def _on_sync_done(self, stats):
        # Worker가 별도 DB 연결에서 작업했으므로 메인 스레드 엔진/관리자 새로고침
        self.sidebar.set_sync_running(False)
        self.reset_db_connection(self.conn, show_all_if_no_query=True)
        self.sidebar.update_sync_status(stats.get("message", "동기화 완료"), True)
        self._update_auto_sync_countdown()

    def _on_sync_error(self, error):
        self.sidebar.set_sync_running(False)
        self.sidebar.update_sync_status(f"오류: {error}", False)
        self._update_auto_sync_countdown()

    # ═══ 메일 ═══

    def _on_mail_selected(self, r):
        self.mail_preview.show_result(r)

    def _on_open_in_outlook(self, eid):
        if eid:
            try:
                from core.outlook_connector import create_connector
                c = create_connector(use_mock=self.use_mock)
                c.connect()
                c.open_mail_in_outlook(eid)
            except Exception as e: logger.error(f"Outlook 열기 실패: {e}")

    # ═══ 유틸 ═══

    def _update_sidebar(self):
        try:
            self.sidebar.update_folder_counts(self.engine.get_folder_counts())
            self.sidebar.update_sync_status(f"총 {self.engine.get_total_count():,}건 인덱싱됨", True)
        except: pass

    def _focus_search(self):
        self.search_bar.search_input.setFocus()
        self.search_bar.search_input.selectAll()

    def _select_next(self):
        i = self.result_list.selected_index
        if i < len(self.result_list.cards) - 1: self.result_list.select_index(i + 1)

    def _select_prev(self):
        i = self.result_list.selected_index
        if i > 0: self.result_list.select_index(i - 1)

    def _on_escape(self):
        self.search_bar.search_input.clearFocus()

    # ═══ 창 닫기 → 트레이로 최소화 ═══

    def set_tray_mode(self, enabled: bool):
        """트레이 모드 설정 — True면 X 클릭 시 트레이로, False면 종료"""
        self._tray_mode = enabled

    def closeEvent(self, event):
        """X 버튼 클릭 시: 트레이 모드면 숨기기, 아니면 종료"""
        if getattr(self, '_tray_mode', False):
            event.ignore()
            self.hide()
            # 트레이 알림 (첫 1회만)
            if not getattr(self, '_tray_notified', False):
                self._tray_notified = True
        else:
            event.accept()
