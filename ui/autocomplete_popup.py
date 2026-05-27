"""
OutLook AnyFinder Ver0.9 for SESUNG Team
자동완성 드롭다운 팝업 위젯
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint
from PyQt6.QtGui import QFont, QCursor

from ui.theme import Colors, Fonts, Radius
from data.models import SearchHistoryItem


class AutocompletePopup(QWidget):
    """
    검색 바 아래에 표시되는 자동완성 드롭다운.
    ↑↓ 키보드 네비게이션, Enter 선택, Esc 닫기, X 삭제.
    """
    item_selected = pyqtSignal(str)   # 선택된 키워드
    item_deleted = pyqtSignal(str)    # 삭제 요청된 키워드

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {Colors.BG_ELEVATED};
                border: 1px solid {Colors.BORDER_LIGHT};
                border-radius: {Radius.MD}px;
            }}
        """)
        self.items_data = []
        self._selected_idx = -1
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(2)

        self.header = QLabel("최근 검색")
        self.header.setFont(QFont("Segoe UI", Fonts.SIZE_XS))
        self.header.setStyleSheet(f"color:{Colors.TEXT_MUTED};padding:4px 8px;background:transparent;border:none;")
        layout.addWidget(self.header)

        self.list_container = QVBoxLayout()
        self.list_container.setSpacing(1)
        self.list_container.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.list_container)

    def show_suggestions(self, suggestions: list, prefix: str = ""):
        """자동완성 후보 목록 표시"""
        # 기존 제거
        while self.list_container.count():
            item = self.list_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.items_data = suggestions
        self._selected_idx = -1

        if not suggestions:
            self.hide()
            return

        self.header.setText("최근 검색" if not prefix else f'"{prefix}" 자동완성')

        for i, item in enumerate(suggestions):
            row = self._make_row(item, i)
            self.list_container.addWidget(row)

        self.adjustSize()
        self.show()

    def _make_row(self, item: SearchHistoryItem, idx: int):
        row = QWidget()
        row.setStyleSheet(f"""
            QWidget {{
                background: transparent;
                border-radius: 6px;
                border: none;
            }}
            QWidget:hover {{
                background: {Colors.BG_CARD_HOVER};
            }}
        """)
        row.setFixedHeight(32)
        row.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        h = QHBoxLayout(row)
        h.setContentsMargins(10, 0, 6, 0)
        h.setSpacing(6)

        icon = QLabel("🕐")
        icon.setFixedWidth(16)
        icon.setStyleSheet("background:transparent;border:none;")
        h.addWidget(icon)

        kw_label = QLabel(item.keyword)
        kw_label.setFont(QFont("Segoe UI", Fonts.SIZE_SM))
        kw_label.setStyleSheet(f"color:{Colors.TEXT_PRIMARY};background:transparent;border:none;")
        h.addWidget(kw_label, 1)

        count_label = QLabel(f"{item.search_count}회")
        count_label.setFont(QFont("Segoe UI", Fonts.SIZE_XS))
        count_label.setStyleSheet(f"color:{Colors.TEXT_MUTED};background:transparent;border:none;")
        h.addWidget(count_label)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(20, 20)
        del_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background:transparent; color:{Colors.TEXT_MUTED};
                border:none; border-radius:10px; font-size:11px;
            }}
            QPushButton:hover {{
                background:{Colors.DANGER}33; color:{Colors.DANGER};
            }}
        """)
        del_btn.clicked.connect(lambda: self.item_deleted.emit(item.keyword))
        h.addWidget(del_btn)

        row.mousePressEvent = lambda e, kw=item.keyword: self.item_selected.emit(kw)
        return row

    def select_next(self):
        """↓ 키: 다음 항목 선택"""
        if not self.items_data:
            return ""
        self._selected_idx = min(self._selected_idx + 1, len(self.items_data) - 1)
        self._highlight_selected()
        return self.items_data[self._selected_idx].keyword

    def select_prev(self):
        """↑ 키: 이전 항목 선택"""
        if not self.items_data:
            return ""
        self._selected_idx = max(self._selected_idx - 1, 0)
        self._highlight_selected()
        return self.items_data[self._selected_idx].keyword

    def get_selected(self) -> str:
        """현재 선택된 키워드"""
        if 0 <= self._selected_idx < len(self.items_data):
            return self.items_data[self._selected_idx].keyword
        return ""

    def _highlight_selected(self):
        for i in range(self.list_container.count()):
            w = self.list_container.itemAt(i).widget()
            if w:
                if i == self._selected_idx:
                    w.setStyleSheet(f"QWidget{{background:{Colors.PRIMARY_BG};border-radius:6px;border:none;}}")
                else:
                    w.setStyleSheet(f"QWidget{{background:transparent;border-radius:6px;border:none;}}QWidget:hover{{background:{Colors.BG_CARD_HOVER};}}")

    def position_below(self, widget):
        """위젯 아래에 팝업 위치 설정"""
        pos = widget.mapToGlobal(QPoint(0, widget.height() + 4))
        self.move(pos)
        self.setFixedWidth(widget.width())
