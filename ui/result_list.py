"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[U05] 검색 결과 리스트
"""

from typing import List
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QCursor

from ui.theme import Colors, Fonts
from ui.mail_card import MailCard
from data.models import SearchResult


class ResultList(QWidget):
    """검색 결과 카드 리스트 (스크롤 + 페이지네이션)"""
    mail_selected = pyqtSignal(object)  # SearchResult
    page_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self.cards: List[MailCard] = []
        self._page = 1
        self._total_pages = 1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background:transparent;border:none;")

        self.container = QWidget()
        self.container.setStyleSheet("background:transparent;")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(2, 2, 8, 2)
        self.container_layout.setSpacing(10)
        self.container_layout.addStretch()

        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)

        # 페이지 컨트롤
        self.page_bar = QWidget()
        self.page_bar.setStyleSheet("background:transparent;")
        page_layout = QHBoxLayout(self.page_bar)
        page_layout.setContentsMargins(0, 0, 6, 0)
        page_layout.setSpacing(8)
        page_layout.addStretch()

        self.first_btn = self._page_button("⏮ 맨처음")
        self.first_btn.clicked.connect(lambda: self._request_page(1))
        page_layout.addWidget(self.first_btn)

        self.prev_btn = self._page_button("◀ 이전")
        self.prev_btn.clicked.connect(lambda: self._request_page(self._page - 1))
        page_layout.addWidget(self.prev_btn)

        self.page_label = QLabel("1 / 1")
        self.page_label.setFont(QFont("Segoe UI", Fonts.SIZE_SM, QFont.Weight.Bold))
        self.page_label.setStyleSheet(f"color:{Colors.TEXT_SECONDARY};background:transparent;border:none;")
        page_layout.addWidget(self.page_label)

        self.next_btn = self._page_button("다음 ▶")
        self.next_btn.clicked.connect(lambda: self._request_page(self._page + 1))
        page_layout.addWidget(self.next_btn)

        self.last_btn = self._page_button("마지막 ⏭")
        self.last_btn.clicked.connect(lambda: self._request_page(self._total_pages))
        page_layout.addWidget(self.last_btn)

        page_layout.addStretch()
        layout.addWidget(self.page_bar)
        self.page_bar.hide()

    def clear_results(self, message: str = "검색어를 입력한 뒤 검색 버튼을 눌러 주세요 🔍"):
        """시작 시 이전 검색 결과를 보여주지 않기 위한 빈 상태 표시."""
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.cards.clear()
        empty = QLabel(message)
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setFont(QFont("Segoe UI", Fonts.SIZE_BASE))
        empty.setStyleSheet(f"color:{Colors.TEXT_DIM};padding:60px 20px;background:transparent;")
        self.container_layout.addWidget(empty)
        self.container_layout.addStretch()
        self.set_pagination(1, 1, 0)
        self.page_bar.hide()

    def set_results(self, results: List[SearchResult], search_term: str = ""):
        """결과 리스트 갱신"""
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.cards.clear()

        if not results:
            empty = QLabel("검색 결과가 없습니다\n\n다른 검색어를 시도해 보세요 🔍")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setFont(QFont("Segoe UI", Fonts.SIZE_BASE))
            empty.setStyleSheet(f"color:{Colors.TEXT_DIM};padding:60px 20px;background:transparent;")
            self.container_layout.addWidget(empty)
            self.container_layout.addStretch()
            self.scroll.verticalScrollBar().setValue(0)
            return

        for r in results:
            card = MailCard(r, search_term)
            card.clicked.connect(self._on_card_click)
            self.cards.append(card)
            self.container_layout.addWidget(card)

        self.container_layout.addStretch()
        self.scroll.verticalScrollBar().setValue(0)

        if self.cards:
            self.cards[0].set_selected(True)
            self.mail_selected.emit(self.cards[0].result)

    def set_pagination(self, page: int, total_pages: int, total_count: int = 0):
        self._page = max(1, page)
        self._total_pages = max(1, total_pages)
        self.page_label.setText(f"{self._page:,} / {self._total_pages:,}")
        self.first_btn.setEnabled(self._page > 1)
        self.prev_btn.setEnabled(self._page > 1)
        self.next_btn.setEnabled(self._page < self._total_pages)
        self.last_btn.setEnabled(self._page < self._total_pages)
        self.page_bar.setVisible(self._total_pages > 1)

    def _request_page(self, page: int):
        if 1 <= page <= self._total_pages and page != self._page:
            self.page_requested.emit(page)

    def _page_button(self, text):
        btn = QPushButton(text)
        btn.setFixedHeight(28)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setStyleSheet(f"""
            QPushButton{{background:{Colors.BG_CARD};color:{Colors.TEXT_SECONDARY};border:1px solid {Colors.BORDER};border-radius:6px;padding:4px 12px;font-size:{Fonts.SIZE_SM}px;}}
            QPushButton:hover{{background:{Colors.BG_CARD_HOVER};color:{Colors.TEXT_PRIMARY};}}
            QPushButton:disabled{{color:{Colors.TEXT_MUTED};background:transparent;border-color:{Colors.BORDER};}}
        """)
        return btn

    def _on_card_click(self, result: SearchResult):
        for card in self.cards:
            card.set_selected(card.result is result)
        self.mail_selected.emit(result)

    def select_index(self, idx: int):
        if 0 <= idx < len(self.cards):
            for i, card in enumerate(self.cards):
                card.set_selected(i == idx)
            self.mail_selected.emit(self.cards[idx].result)
            self.scroll.ensureWidgetVisible(self.cards[idx])

    @property
    def selected_index(self) -> int:
        for i, card in enumerate(self.cards):
            if card._selected:
                return i
        return -1
