"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[U02] 사이드바 — 폴더 트리, 북마크, 동기화 상태, 설정
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QCursor

from ui.theme import Colors, Fonts, Radius, APP_NAME, APP_VERSION, APP_SUBTITLE


class SidebarButton(QPushButton):
    def __init__(self, icon, text, parent=None):
        super().__init__(f"{icon}  {text}", parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(36)
        self.setFont(QFont("Segoe UI", Fonts.SIZE_BASE))
        self._active = False
        self._apply()

    def set_active(self, active):
        self._active = active
        self._apply()

    def _apply(self):
        if self._active:
            self.setStyleSheet(f"QPushButton{{background:{Colors.PRIMARY_BG};color:{Colors.PRIMARY_HOVER};border:1px solid {Colors.PRIMARY}35;border-radius:{Radius.SM}px;text-align:left;padding-left:14px;font-weight:bold;}}QPushButton:hover{{border:1px solid {Colors.PRIMARY}70;}}")
        else:
            self.setStyleSheet(f"QPushButton{{background:transparent;color:{Colors.TEXT_DIM};border:1px solid transparent;border-radius:{Radius.SM}px;text-align:left;padding-left:14px;}}QPushButton:hover{{background:{Colors.BG_CARD_HOVER};color:{Colors.TEXT_SECONDARY};border:1px solid {Colors.BORDER_LIGHT};}}")


class Sidebar(QWidget):
    """사이드바"""
    page_changed = pyqtSignal(str)
    sync_requested = pyqtSignal()
    sync_stop_requested = pyqtSignal()
    folder_selected = pyqtSignal(str)       # 폴더 이름
    bookmark_selected = pyqtSignal(int)      # 북마크 ID
    settings_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(260)
        self.setStyleSheet(f"background-color:{Colors.BG_SIDEBAR};border-right:1px solid {Colors.BORDER};")
        self.buttons = {}
        self.folder_buttons = {}
        self.bookmark_widgets = []
        self._sync_running = False
        self._build()
        self._set_active("search")

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(3)

        # 로고
        logo = QLabel(f"📧 {APP_NAME}")
        logo.setFont(QFont("Segoe UI", Fonts.SIZE_XL, QFont.Weight.Bold))
        logo.setStyleSheet(f"color:{Colors.PRIMARY_HOVER};padding:4px;background:transparent;border:none;")
        layout.addWidget(logo)

        ver = QLabel(f"{APP_VERSION} {APP_SUBTITLE}")
        ver.setFont(QFont("Segoe UI", Fonts.SIZE_XS))
        ver.setStyleSheet(f"color:{Colors.TEXT_MUTED};padding-left:4px;background:transparent;border:none;")
        layout.addWidget(ver)

        layout.addSpacing(14)

        # 검색 섹션
        layout.addWidget(self._section("검색"))
        btn = SidebarButton("🔍", "전체 검색")
        btn.clicked.connect(lambda: self._on_click("search"))
        self.buttons["search"] = btn
        layout.addWidget(btn)

        layout.addSpacing(6)

        # 북마크 섹션
        layout.addWidget(self._section("북마크"))
        self.bookmark_container = QVBoxLayout()
        self.bookmark_container.setSpacing(2)
        self.bookmark_container.setContentsMargins(0, 0, 0, 0)
        bm_widget = QWidget()
        bm_widget.setStyleSheet("background:transparent;border:none;")
        bm_widget.setLayout(self.bookmark_container)
        layout.addWidget(bm_widget)

        self.no_bookmark_label = QLabel("  아직 북마크가 없습니다")
        self.no_bookmark_label.setFont(QFont("Segoe UI", Fonts.SIZE_XS))
        self.no_bookmark_label.setStyleSheet(f"color:{Colors.TEXT_MUTED};background:transparent;border:none;padding:4px 0;")
        self.bookmark_container.addWidget(self.no_bookmark_label)

        layout.addSpacing(6)

        # 폴더 섹션
        layout.addWidget(self._section("폴더"))
        folders = [
            ("inbox",  "📥", "받은편지함"),
            ("sent",   "📤", "보낸편지함"),
            ("drafts", "📝", "임시보관함"),
            ("trash",  "🗑", "지운편지함"),
        ]
        for key, icon, name in folders:
            row = QWidget()
            row.setStyleSheet("background:transparent;border:none;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(0)

            fb = SidebarButton(icon, name)
            fb.clicked.connect(lambda checked, n=name: self._on_folder_click(n))
            self.buttons[key] = fb
            self.folder_buttons[key] = fb
            rl.addWidget(fb, 1)

            cnt = QLabel("—")
            cnt.setObjectName(f"cnt_{key}")
            cnt.setFont(QFont("Segoe UI", Fonts.SIZE_XS))
            cnt.setStyleSheet(f"color:{Colors.TEXT_DIM};padding-right:6px;background:transparent;border:none;font-weight:bold;")
            cnt.setFixedWidth(58)
            cnt.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            rl.addWidget(cnt)
            layout.addWidget(row)

        # 지운 편지함 아래 실시간 동기화 진행 표시
        self.sync_progress_card = QWidget()
        self.sync_progress_card.setStyleSheet(f"background:{Colors.BG_CARD};border:1px solid {Colors.BORDER};border-radius:{Radius.MD}px;")
        spl = QVBoxLayout(self.sync_progress_card)
        spl.setContentsMargins(10, 8, 10, 8)
        spl.setSpacing(5)

        self.sync_progress_title = QLabel("동기화 진행 중")
        self.sync_progress_title.setFont(QFont("Segoe UI", Fonts.SIZE_XS, QFont.Weight.Bold))
        self.sync_progress_title.setStyleSheet(f"color:{Colors.TEXT_SECONDARY};background:transparent;border:none;")
        spl.addWidget(self.sync_progress_title)

        prow = QHBoxLayout()
        self.sync_progress_bar = QProgressBar()
        self.sync_progress_bar.setFixedHeight(8)
        self.sync_progress_bar.setRange(0, 100)
        self.sync_progress_bar.setValue(0)
        self.sync_progress_bar.setTextVisible(False)
        self.sync_progress_bar.setStyleSheet(f"""
            QProgressBar {{ background:{Colors.BG_INPUT}; border:none; border-radius:4px; }}
            QProgressBar::chunk {{ background:{Colors.PRIMARY}; border-radius:4px; }}
        """)
        prow.addWidget(self.sync_progress_bar, 1)
        self.sync_progress_pct = QLabel("0%")
        self.sync_progress_pct.setFixedWidth(38)
        self.sync_progress_pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.sync_progress_pct.setFont(QFont("Segoe UI", Fonts.SIZE_XS, QFont.Weight.Bold))
        self.sync_progress_pct.setStyleSheet(f"color:{Colors.PRIMARY_HOVER};background:transparent;border:none;")
        prow.addWidget(self.sync_progress_pct)
        spl.addLayout(prow)

        self.sync_progress_msg = QLabel("대기 중")
        self.sync_progress_msg.setFont(QFont("Segoe UI", Fonts.SIZE_XS))
        self.sync_progress_msg.setWordWrap(True)
        self.sync_progress_msg.setStyleSheet(f"color:{Colors.TEXT_DIM};background:transparent;border:none;")
        spl.addWidget(self.sync_progress_msg)
        self.sync_progress_card.hide()
        layout.addWidget(self.sync_progress_card)

        layout.addStretch()

        # 동기화 상태
        sync_card = QWidget()
        sync_card.setStyleSheet(f"background:{Colors.BG_CARD};border:1px solid {Colors.BORDER};border-radius:{Radius.MD}px;")
        sl = QVBoxLayout(sync_card)
        sl.setContentsMargins(10, 8, 10, 8)
        sl.setSpacing(3)

        sh = QHBoxLayout()
        sh.addWidget(self._tiny_lbl("🔄 동기화", Fonts.SIZE_SM, Colors.TEXT_SECONDARY, bold=True))
        self.sync_dot = QLabel("●")
        self.sync_dot.setStyleSheet(f"color:{Colors.SUCCESS};font-size:10px;background:transparent;border:none;")
        sh.addStretch()
        sh.addWidget(self.sync_dot)
        sl.addLayout(sh)

        self.sync_info = QLabel("준비 중...")
        self.sync_info.setFont(QFont("Segoe UI", Fonts.SIZE_XS))
        self.sync_info.setStyleSheet(f"color:{Colors.TEXT_DIM};background:transparent;border:none;")
        sl.addWidget(self.sync_info)

        self.sync_btn = QPushButton("동기화 시작")
        self.sync_btn.setFixedHeight(26)
        self.sync_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.sync_btn.setStyleSheet(f"QPushButton{{background:transparent;color:{Colors.ACCENT};border:1px solid {Colors.ACCENT}40;border-radius:7px;font-size:{Fonts.SIZE_XS}px;padding:2px 6px;}}QPushButton:hover{{background:transparent;border:2px solid {Colors.ACCENT};}}QPushButton:disabled{{color:{Colors.TEXT_MUTED};border-color:{Colors.BORDER};background:transparent;}}")
        self.sync_btn.clicked.connect(self.sync_requested.emit)
        sl.addWidget(self.sync_btn)

        self.sync_stop_btn = QPushButton("⏹ 동기화 중지")
        self.sync_stop_btn.setFixedHeight(26)
        self.sync_stop_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.sync_stop_btn.setStyleSheet(f"QPushButton{{background:transparent;color:{Colors.DANGER};border:1px solid {Colors.DANGER}55;border-radius:7px;font-size:{Fonts.SIZE_XS}px;padding:2px 6px;}}QPushButton:hover{{background:transparent;border:2px solid {Colors.DANGER};}}")
        self.sync_stop_btn.clicked.connect(self.sync_stop_requested.emit)
        self.sync_stop_btn.hide()
        sl.addWidget(self.sync_stop_btn)

        layout.addWidget(sync_card)
        layout.addSpacing(6)

        # 설정
        settings_btn = SidebarButton("⚙", "설정")
        settings_btn.clicked.connect(self.settings_clicked.emit)
        self.buttons["settings"] = settings_btn
        layout.addWidget(settings_btn)

    # ── 공개 메서드 ──

    def update_folder_counts(self, counts: dict):
        """폴더별 메일 수 업데이트.

        Outlook/버전별로 '받은편지함'과 '받은 편지함'처럼 공백이 다른 이름이
        섞여 저장될 수 있으므로 대표 폴더는 별칭을 합산한다.
        """
        aliases = {
            "inbox": ["받은편지함", "받은 편지함", "Inbox"],
            "sent": ["보낸편지함", "보낸 편지함", "Sent Items", "Sent"],
            "drafts": ["임시보관함", "임시 보관함", "Drafts"],
            "trash": ["지운편지함", "지운 편지함", "Deleted Items", "Trash"],
        }
        for key, names in aliases.items():
            lbl = self.findChild(QLabel, f"cnt_{key}")
            if lbl:
                cnt = sum(counts.get(name, 0) for name in names)
                lbl.setText(f"{cnt:,}" if cnt else "—")

    def update_sync_status(self, message: str, ok: bool = True):
        # 동기화 실행 중에는 상세 작업현황을 하단 '동기화' 섹션에 중복 표시하지 않는다.
        # 진행 상세는 지운 편지함 아래 진행 표시창(update_sync_progress)에만 표시한다.
        if getattr(self, "_sync_running", False):
            return
        self.sync_info.setText(message)
        self.sync_dot.setStyleSheet(f"color:{Colors.SUCCESS if ok else Colors.DANGER};font-size:10px;background:transparent;border:none;")

    def set_sync_running(self, running: bool, message: str = None):
        """동기화 실행 중 UI 상태 전환.

        진행 상세 메시지는 지운 편지함 아래의 진행 표시창에만 표시하고,
        하단 '동기화' 섹션에는 중복 작업현황 메시지를 표시하지 않는다.
        """
        self._sync_running = running
        self.sync_btn.setEnabled(not running)
        self.sync_stop_btn.setVisible(running)
        self.sync_progress_card.setVisible(running)
        if running:
            self.sync_info.setText("")
            if message:
                self.sync_progress_msg.setText(message)
            self.sync_dot.setStyleSheet(f"color:{Colors.WARNING};font-size:10px;background:transparent;border:none;")
        else:
            if message:
                self.update_sync_status(message, True)
            self.sync_progress_bar.setRange(0, 100)
            self.sync_progress_bar.setValue(0)
            self.sync_progress_pct.setText("0%")
            self.sync_progress_msg.setText("대기 중")

    def update_sync_progress(self, done: int, total: int, message: str = "", folder: str = ""):
        """지운 편지함 아래 진행 그래프/퍼센트 갱신."""
        self.sync_progress_card.show()
        if total and total > 0:
            pct = max(0, min(100, int(done / total * 100)))
            self.sync_progress_bar.setRange(0, 100)
            self.sync_progress_bar.setValue(pct)
            self.sync_progress_pct.setText(f"{pct}%")
        else:
            # 총량 계산 전에는 움직이는 busy indicator로 표시
            self.sync_progress_bar.setRange(0, 0)
            self.sync_progress_pct.setText("…")
        title = "동기화 진행 중"
        if folder:
            title += f" · {folder}"
        self.sync_progress_title.setText(title)
        if message:
            self.sync_progress_msg.setText(message)

    def update_sync_mode(self, mode_text: str):
        """동기화 모드 표시 (자동/수동)"""
        if getattr(self, "_sync_running", False):
            return
        try:
            self.sync_info.setText(f"{self.sync_info.text().split('·')[0].strip()} · {mode_text}")
        except Exception:
            pass

    def update_bookmarks(self, bookmarks: list):
        """북마크 목록 갱신"""
        # 기존 제거
        for w in self.bookmark_widgets:
            w.deleteLater()
        self.bookmark_widgets.clear()

        if not bookmarks:
            self.no_bookmark_label.show()
            return

        self.no_bookmark_label.hide()
        for bm in bookmarks:
            btn = SidebarButton("⭐", bm.name)
            btn.clicked.connect(lambda checked, b=bm: self.bookmark_selected.emit(b.id))
            self.bookmark_container.addWidget(btn)
            self.bookmark_widgets.append(btn)

    # ── 내부 ──

    def _on_click(self, key):
        self._set_active(key)
        self.page_changed.emit(key)

    def _on_folder_click(self, folder_name):
        self.folder_selected.emit(folder_name)

    def _set_active(self, active_key):
        for k, b in self.buttons.items():
            b.set_active(k == active_key)

    def _section(self, text):
        lbl = QLabel(text)
        lbl.setFont(QFont("Segoe UI", Fonts.SIZE_XS, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{Colors.TEXT_MUTED};padding:6px 4px 3px;background:transparent;border:none;letter-spacing:1px;")
        return lbl

    def _tiny_lbl(self, text, size, color, bold=False):
        lbl = QLabel(text)
        w = QFont.Weight.Bold if bold else QFont.Weight.Normal
        lbl.setFont(QFont("Segoe UI", size, w))
        lbl.setStyleSheet(f"color:{color};background:transparent;border:none;")
        return lbl
