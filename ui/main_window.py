"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[U01] 메인 윈도우 (v4 — 설정 반영 + 동기화 모드 토글 + 세션 정리)
"""

import json
import logging

from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut

from ui.theme import Colors, APP_FULL_NAME, global_stylesheet
from ui.sidebar import Sidebar
from ui.search_bar import SearchBar
from ui.filter_bar import FilterBar
from ui.result_list import ResultList
from ui.mail_preview import MailPreview
from ui.autocomplete_popup import AutocompletePopup
from core.search_engine import SearchEngine
from core.autocomplete import AutocompleteEngine
from core.bookmark_manager import BookmarkManager
from core.related_keywords import RelatedKeywordsEngine
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
        self.autocomplete = AutocompleteEngine(db_conn)
        self.bookmarks = BookmarkManager(db_conn)
        self.related_kw = RelatedKeywordsEngine(db_conn)
        self.related_kw.seed_default_relations()

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
        self._setup_autocomplete()
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
        self.search_bar.match_mode_changed.connect(self._on_match_mode_changed)
        self.filter_bar.filter_changed.connect(self._on_filter_changed)
        self.filter_bar.sort_changed.connect(self._on_sort_changed)
        self.result_list.mail_selected.connect(self._on_mail_selected)
        self.mail_preview.open_in_outlook.connect(self._on_open_in_outlook)
        self.sidebar.folder_selected.connect(self._on_folder_selected)
        self.sidebar.sync_requested.connect(self._on_sync_requested)
        self.sidebar.bookmark_selected.connect(self._on_bookmark_selected)

        QShortcut(QKeySequence("Ctrl+K"), self).activated.connect(self._focus_search)
        QShortcut(QKeySequence("Ctrl+J"), self).activated.connect(self._select_next)
        QShortcut(QKeySequence("Ctrl+Shift+J"), self).activated.connect(self._select_prev)
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._on_escape)

    def _setup_autocomplete(self):
        self.ac_popup = AutocompletePopup(self)
        self.ac_popup.item_selected.connect(self._on_ac_selected)
        self.ac_popup.item_deleted.connect(self._on_ac_deleted)
        self._ac_timer = QTimer()
        self._ac_timer.setSingleShot(True)
        self._ac_timer.setInterval(300)
        self._ac_timer.timeout.connect(self._show_ac)
        self.search_bar.search_input.textChanged.connect(self._on_text_changed)
        self.search_bar.search_input.installEventFilter(self)

    def _setup_auto_sync(self):
        """자동 동기화 타이머 — 프로그램 시작 시 비활성화 (사용자 승인 필요)"""
        self._sync_timer = QTimer()
        # ★ 시작 시 자동 동기화 비활성화 — 사용자가 수동으로만 트리거
        logger.info("자동 동기화 비활성화 — 사용자가 [지금 동기화]로 수동 실행")

    def _apply_sync_settings(self):
        """현재 config 기준으로 동기화 타이머 재설정"""
        auto = self.config.get("sync", {}).get("auto_sync", True)
        interval = self.config.get("sync", {}).get("interval_minutes", 10)

        self._sync_timer.stop()

        if auto and interval > 0:
            self._sync_timer.setInterval(interval * 60 * 1000)
            self._sync_timer.timeout.connect(self._on_auto_sync)
            self._sync_timer.start()
            mode_text = f"자동 ({interval}분 주기)"
            logger.info(f"동기화 모드: 자동 {interval}분")
        else:
            mode_text = "수동"
            logger.info("동기화 모드: 수동")

        self.sidebar.update_sync_mode(mode_text)

    def apply_new_settings(self, new_config: dict):
        """설정 변경 시 호출 — 타이머 재설정 등"""
        self.config = new_config
        self._apply_sync_settings()
        logger.info("설정 반영 완료")

    def _apply_global_style(self):
        self.setStyleSheet(global_stylesheet())

    def _initial_load(self):
        self.filter_bar.load_extensions_from_db(self.conn)  # ★ 동적 확장자 로드
        self._execute_search("", default_sort="received_at_desc")
        self._update_sidebar()
        self._refresh_bookmarks()

    # ═══ 자동완성 ═══

    def eventFilter(self, obj, event):
        if obj == self.search_bar.search_input:
            from PyQt6.QtCore import QEvent
            if event.type() == QEvent.Type.KeyPress:
                k = event.key()
                if self.ac_popup.isVisible():
                    if k == Qt.Key.Key_Down:
                        kw = self.ac_popup.select_next()
                        if kw:
                            self.search_bar.search_input.blockSignals(True)
                            self.search_bar.search_input.setText(kw)
                            self.search_bar.search_input.blockSignals(False)
                        return True
                    elif k == Qt.Key.Key_Up:
                        kw = self.ac_popup.select_prev()
                        if kw:
                            self.search_bar.search_input.blockSignals(True)
                            self.search_bar.search_input.setText(kw)
                            self.search_bar.search_input.blockSignals(False)
                        return True
                    elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                        sel = self.ac_popup.get_selected()
                        if sel:
                            self.search_bar.search_input.setText(sel)
                            self.ac_popup.hide()
                            self._on_search(sel)
                            return True
                    elif k == Qt.Key.Key_Escape:
                        self.ac_popup.hide()
                        return True
        return super().eventFilter(obj, event)

    def _on_text_changed(self, text):
        if text.strip(): self._ac_timer.start()
        else: self.ac_popup.hide()

    def _show_ac(self):
        text = self.search_bar.search_input.text().strip()
        if not text: self.ac_popup.hide(); return
        sug = self.autocomplete.get_suggestions(text)
        if sug:
            self.ac_popup.show_suggestions(sug, text)
            self.ac_popup.position_below(self.search_bar.search_input)
        else: self.ac_popup.hide()

    def _on_ac_selected(self, kw):
        self.search_bar.search_input.setText(kw)
        self.ac_popup.hide()
        self._on_search(kw)

    def _on_ac_deleted(self, kw):
        self.autocomplete.delete_item(kw)
        self._show_ac()

    # ═══ 검색 ═══

    def _on_search(self, query):
        self.ac_popup.hide()
        self._current_query = query
        self._current_page = 1
        self._execute_search(query)
        if query.strip():
            self.autocomplete.record_search(query.strip())
            self.related_kw.record_session(query.strip())
        self.search_bar.set_bookmark_active(self.bookmarks.is_bookmarked(query) if query else False)
        if query.strip():
            self.search_bar.set_related_keywords(self.related_kw.get_related(query.strip()))
        else:
            self.search_bar.set_related_keywords([])

    def _on_filter_changed(self):
        self._current_page = 1
        self._execute_search(self._current_query)

    def _on_match_mode_changed(self, mode):
        """매칭 모드 변경 시 재검색"""
        self._current_page = 1
        self._execute_search(self._current_query)

    def _on_sort_changed(self, _):
        self._current_page = 1
        self._execute_search(self._current_query)

    def _on_folder_selected(self, folder_name):
        self.search_bar.search_input.setText("")
        self._current_query = ""
        self.filter_bar.reset_all()
        self._execute_search("", extra_filters=[("folder_name = ?", [folder_name])])

    def _execute_search(self, query, extra_filters=None, default_sort=None):
        sort = default_sort or self.filter_bar.get_sort_mode()
        # 매칭 모드에 따른 쿼리 변환
        actual_query = self._apply_match_mode(query)
        where = self._build_where(extra_filters)
        try:
            resp = self.engine.search(query=actual_query, page=self._current_page, per_page=20, sort_by=sort, extra_where=where)
            self.result_list.set_results(resp.results, query)  # 하이라이트는 원본 쿼리
            total_db = self.engine.get_total_count()
            self.filter_bar.set_result_count(total_db, resp.total_count, resp.elapsed_ms, "FTS5" if query else "전체")
        except Exception as e:
            logger.error(f"검색 오류: {e}")

    def _apply_match_mode(self, query: str) -> str:
        """매칭 모드에 따라 쿼리 변환"""
        if not query or not query.strip():
            return query
        mode = self.search_bar.get_match_mode()
        words = query.strip().split()
        if len(words) <= 1:
            return query
        if mode == "all":    # AND (기본)
            return query     # query_parser가 기본 AND 처리
        elif mode == "any":  # OR
            return " OR ".join(words)
        elif mode == "exact":  # 정확히 일치 (구문 검색)
            return f'"{query.strip()}"'
        return query

    def _build_where(self, extra=None):
        w = extra or []
        a = self.filter_bar.get_active_filters()
        if a.get("inbox"): w.append(("folder_name = ?", ["받은편지함"]))
        if a.get("sent"): w.append(("folder_name = ?", ["보낸편지함"]))
        # has_att는 DynamicAttachmentFilter에서 처리
        if a.get("unread"): w.append(("is_read = ?", [0]))
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
        self._run_sync()

    def _run_sync(self):
        from workers.sync_worker import SyncWorker
        if self._sync_worker and self._sync_worker.isRunning():
            return
        self.sidebar.update_sync_status("동기화 중...", True)
        fids = self.config.get("indexing", {}).get("folder_ids", [6, 5])
        inc = self.config.get("indexing", {}).get("include_subfolders", True)
        self._sync_worker = SyncWorker(db_path=self.db_path, use_mock=self.use_mock, folder_ids=fids, include_subfolders=inc)
        self._sync_worker.sync_progress.connect(lambda d, t, m: self.sidebar.update_sync_status(m, True))
        self._sync_worker.sync_finished.connect(self._on_sync_done)
        self._sync_worker.sync_error.connect(lambda e: self.sidebar.update_sync_status(f"오류: {e}", False))
        self._sync_worker.start()

    def _on_sync_done(self, stats):
        # Worker가 별도 DB 연결에서 작업했으므로 메인 스레드 엔진 새로고침
        self.engine = SearchEngine(self.conn)
        self.sidebar.update_sync_status(stats.get("message", "동기화 완료"), True)
        self._execute_search(self._current_query)
        self._update_sidebar()

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
        if self.ac_popup.isVisible(): self.ac_popup.hide()

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
