"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[U03] 검색 바 (v3 — 매칭 모드 추가 + 레퍼런스 UI 반영)

레퍼런스 벤치마킹:
  - [모두 포함] / [하나 이상] / [정확히 일치] 매칭 모드 토글
  - 검색 결과 내 재검색
  - 검색어 하이라이트 주황 배경
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QCursor

from ui.theme import Colors, Fonts, Radius


class MatchModeButton(QPushButton):
    """매칭 모드 토글 버튼 [모두 포함] / [하나 이상] / [정확히 일치]"""
    mode_changed = pyqtSignal(str)

    MODES = [
        ("all", "모두 포함"),      # AND
        ("any", "하나 이상"),      # OR
        ("exact", "정확히 일치"),   # PHRASE
    ]

    def __init__(self, parent=None):
        super().__init__("모두 포함", parent)
        self._index = 0
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(26)
        self.setFont(QFont("Segoe UI", Fonts.SIZE_XS, QFont.Weight.Bold))
        self._apply()
        self.clicked.connect(self._cycle)

    def _cycle(self):
        self._index = (self._index + 1) % len(self.MODES)
        key, label = self.MODES[self._index]
        self.setText(label)
        self._apply()
        self.mode_changed.emit(key)

    def get_mode(self) -> str:
        return self.MODES[self._index][0]

    def _apply(self):
        self.setStyleSheet(f"""
            QPushButton{{background:{Colors.SUCCESS};color:#FFF;border:none;border-radius:4px;padding:3px 10px;font-size:{Fonts.SIZE_XS}px;}}
            QPushButton:hover{{background:#34D399;}}
        """)


class SearchBar(QWidget):
    search_triggered = pyqtSignal(str)
    bookmark_clicked = pyqtSignal(str)
    match_mode_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ── Row 1: 북마크 + 검색창 + 매칭모드
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        # 북마크
        self.bookmark_btn = QPushButton("☆")
        self.bookmark_btn.setFixedSize(36, 36)
        self.bookmark_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.bookmark_btn.setToolTip("검색어 북마크")
        self.bookmark_btn.setFont(QFont("Segoe UI", 15))
        self.bookmark_btn.setStyleSheet(f"QPushButton{{background:{Colors.BG_CARD};color:{Colors.TEXT_DIM};border:1px solid {Colors.BORDER};border-radius:8px;}}QPushButton:hover{{color:{Colors.WARNING};border-color:{Colors.WARNING}40;background:{Colors.WARNING_BG};}}")
        self.bookmark_btn.clicked.connect(lambda: self.bookmark_clicked.emit(self.search_input.text()))
        row1.addWidget(self.bookmark_btn)

        # 검색 입력
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("메일 검색... (제목, 본문, 발신자, 첨부)")
        self.search_input.setFixedHeight(36)
        self.search_input.setMaximumWidth(420)
        self.search_input.setFont(QFont("Segoe UI", Fonts.SIZE_BASE))
        self.search_input.setStyleSheet(f"""
            QLineEdit{{background:{Colors.BG_CARD};color:{Colors.TEXT_PRIMARY};border:1px solid {Colors.BORDER};border-radius:8px;padding:0 12px;selection-background-color:{Colors.PRIMARY};}}
            QLineEdit:focus{{border:2px solid {Colors.PRIMARY};background:{Colors.BG_INPUT};}}
        """)
        self.search_input.returnPressed.connect(lambda: self.search_triggered.emit(self.search_input.text()))
        row1.addWidget(self.search_input)

        # ★ 매칭 모드 토글 [모두 포함] / [하나 이상] / [정확히 일치]
        self.match_mode = MatchModeButton()
        self.match_mode.mode_changed.connect(self.match_mode_changed.emit)
        row1.addWidget(self.match_mode)

        # Ctrl+K 힌트
        hint = QLabel("Ctrl+K")
        hint.setFont(QFont("Segoe UI", 9))
        hint.setStyleSheet(f"color:{Colors.TEXT_MUTED};background:{Colors.BG_CARD};border:1px solid {Colors.BORDER};border-radius:3px;padding:1px 5px;")
        hint.setFixedHeight(20)
        row1.addWidget(hint)

        row1.addStretch()
        layout.addLayout(row1)

        # ── Row 2: 연관 검색어
        self.related_widget = QWidget()
        self.related_widget.setStyleSheet("background:transparent;")
        self.related_widget.setFixedHeight(24)
        self.related_layout = QHBoxLayout(self.related_widget)
        self.related_layout.setContentsMargins(42, 0, 0, 0)
        self.related_layout.setSpacing(4)
        self.related_label = QLabel("연관:")
        self.related_label.setFont(QFont("Segoe UI", 9))
        self.related_label.setStyleSheet(f"color:{Colors.TEXT_DIM};background:transparent;")
        self.related_label.setFixedHeight(18)
        self.related_layout.addWidget(self.related_label)
        self.related_layout.addStretch()
        self.related_widget.hide()
        layout.addWidget(self.related_widget)

    def get_match_mode(self) -> str:
        return self.match_mode.get_mode()

    def set_related_keywords(self, keywords):
        while self.related_layout.count() > 2:
            item = self.related_layout.takeAt(self.related_layout.count() - 1)
            if item.widget() and item.widget() != self.related_label:
                item.widget().deleteLater()
        if not keywords:
            self.related_widget.hide(); return
        for kw in keywords[:6]:
            c = QPushButton(kw)
            c.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            c.setFixedHeight(18)
            c.setFont(QFont("Segoe UI", 9))
            c.setStyleSheet(f"QPushButton{{background:{Colors.ACCENT_BG};color:{Colors.ACCENT};border:1px solid {Colors.ACCENT}30;border-radius:3px;padding:0px 6px;}}QPushButton:hover{{background:{Colors.ACCENT}25;}}")
            c.clicked.connect(lambda ch, q=kw: self._on_related(q))
            self.related_layout.insertWidget(self.related_layout.count() - 1, c)
        self.related_widget.show()

    def set_bookmark_active(self, is_bm):
        if is_bm:
            self.bookmark_btn.setText("★")
            self.bookmark_btn.setStyleSheet(f"QPushButton{{background:{Colors.WARNING_BG};color:{Colors.WARNING};border:1px solid {Colors.WARNING}40;border-radius:8px;}}")
        else:
            self.bookmark_btn.setText("☆")
            self.bookmark_btn.setStyleSheet(f"QPushButton{{background:{Colors.BG_CARD};color:{Colors.TEXT_DIM};border:1px solid {Colors.BORDER};border-radius:8px;}}QPushButton:hover{{color:{Colors.WARNING};border-color:{Colors.WARNING}40;background:{Colors.WARNING_BG};}}")

    def _on_related(self, kw):
        self.search_input.setText(kw)
        self.search_triggered.emit(kw)
