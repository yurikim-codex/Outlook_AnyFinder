"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[U05] 검색 결과 리스트
"""

from typing import List
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from ui.theme import Colors, Fonts
from ui.mail_card import MailCard
from data.models import SearchResult


class ResultList(QWidget):
    """검색 결과 카드 리스트 (스크롤)"""
    mail_selected = pyqtSignal(object)  # SearchResult

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self.cards: List[MailCard] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background:transparent;border:none;")

        self.container = QWidget()
        self.container.setStyleSheet("background:transparent;")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 6, 0)
        self.container_layout.setSpacing(6)
        self.container_layout.addStretch()

        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

    def set_results(self, results: List[SearchResult], search_term: str = ""):
        """결과 리스트 갱신"""
        # 기존 카드 제거
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
            return

        for r in results:
            card = MailCard(r, search_term)
            card.clicked.connect(self._on_card_click)
            self.cards.append(card)
            self.container_layout.addWidget(card)

        self.container_layout.addStretch()

        # 첫 번째 자동 선택
        if self.cards:
            self.cards[0].set_selected(True)
            self.mail_selected.emit(self.cards[0].result)

    def _on_card_click(self, result: SearchResult):
        for card in self.cards:
            card.set_selected(card.result is result)
        self.mail_selected.emit(result)

    def select_index(self, idx: int):
        """인덱스로 카드 선택 (키보드 네비게이션)"""
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
