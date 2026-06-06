"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[U03] 검색 바

단순 검색 UI:
  - 북마크 버튼
  - 검색 입력창
  - 검색 버튼
  - 메일 주소 인라인 자동완성(QCompleter InlineCompletion)
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QCompleter, QCheckBox
from PyQt6.QtCore import Qt, pyqtSignal, QStringListModel
from PyQt6.QtGui import QFont, QCursor

from ui.theme import Colors, Fonts


class SearchBar(QWidget):
    search_triggered = pyqtSignal(str)
    bookmark_clicked = pyqtSignal(str)
    # 과거 연결 코드/테스트 호환용. 현재 UI에서는 사용하지 않음.
    match_mode_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self._email_model = QStringListModel([])
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(6)

        self.bookmark_btn = QPushButton("☆")
        self.bookmark_btn.setFixedSize(36, 36)
        self.bookmark_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.bookmark_btn.setToolTip("검색어 북마크")
        self.bookmark_btn.setFont(QFont("Segoe UI", 15))
        self.bookmark_btn.setStyleSheet(
            f"QPushButton{{background:{Colors.BG_CARD};color:{Colors.TEXT_DIM};"
            f"border:1px solid {Colors.BORDER};border-radius:8px;}}"
            f"QPushButton:hover{{color:{Colors.WARNING};border-color:{Colors.WARNING}40;"
            f"background:{Colors.WARNING_BG};}}"
        )
        self.bookmark_btn.clicked.connect(lambda: self.bookmark_clicked.emit(self.search_input.text()))
        row.addWidget(self.bookmark_btn)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("메일 검색... (제목, 본문, 발신자, 첨부파일명, 메일주소)")
        self.search_input.setFixedHeight(36)
        self.search_input.setMinimumWidth(360)
        self.search_input.setFont(QFont("Segoe UI", Fonts.SIZE_BASE))
        self.search_input.setStyleSheet(f"""
            QLineEdit{{background:{Colors.BG_CARD};color:{Colors.TEXT_PRIMARY};border:1px solid {Colors.BORDER};border-radius:8px;padding:0 12px;selection-background-color:{Colors.PRIMARY};}}
            QLineEdit:focus{{border:2px solid {Colors.PRIMARY};background:{Colors.BG_INPUT};}}
        """)
        self.search_input.returnPressed.connect(lambda: self.search_triggered.emit(self.search_input.text()))

        # 메일 주소 자동완성: 팝업 리스트가 아닌 인라인 완성으로 창 이동 시 분리 문제 방지
        self.email_completer = QCompleter(self._email_model, self)
        self.email_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.email_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.email_completer.setCompletionMode(QCompleter.CompletionMode.InlineCompletion)
        self.search_input.setCompleter(self.email_completer)

        row.addWidget(self.search_input, 1)

        self.search_btn = QPushButton("🔍 검색")
        self.search_btn.setFixedHeight(36)
        self.search_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.search_btn.setFont(QFont("Segoe UI", Fonts.SIZE_SM, QFont.Weight.Bold))
        self.search_btn.setStyleSheet(f"""
            QPushButton{{background:{Colors.PRIMARY};color:#FFF;border:1px solid {Colors.PRIMARY};border-radius:10px;padding:0 18px;font-size:{Fonts.SIZE_SM}px;font-weight:bold;}}
            QPushButton:hover{{background:{Colors.PRIMARY_HOVER};border:1px solid {Colors.BORDER_FOCUS};}}
        """)
        self.search_btn.clicked.connect(lambda: self.search_triggered.emit(self.search_input.text()))
        row.addWidget(self.search_btn)

        self.exact_word_check = QCheckBox("정확한 단어만")
        self.exact_word_check.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.exact_word_check.setToolTip("체크 시 정확한 단어 기준으로 검색합니다. 해제 시 검색어가 포함된 단어도 검색합니다. 예: 주관 → 주관기관")
        self.exact_word_check.setFont(QFont("Segoe UI", Fonts.SIZE_SM))
        self.exact_word_check.setStyleSheet(f"""
            QCheckBox{{color:{Colors.TEXT_SECONDARY};spacing:6px;background:transparent;border:none;}}
            QCheckBox::indicator{{width:16px;height:16px;border:1px solid {Colors.BORDER_LIGHT};border-radius:5px;background:{Colors.BG_CARD};}}
            QCheckBox::indicator:checked{{background:{Colors.PRIMARY};border:1px solid {Colors.PRIMARY};}}
            QCheckBox:hover{{color:{Colors.TEXT_PRIMARY};}}
        """)
        self.exact_word_check.stateChanged.connect(lambda _: self.search_triggered.emit(self.search_input.text()) if self.search_input.text().strip() else None)
        row.addWidget(self.exact_word_check)

        row.addStretch()
        layout.addLayout(row)

    def set_email_suggestions(self, emails):
        """메일 주소 인라인 자동완성 후보 갱신."""
        clean = sorted({e.strip() for e in emails if e and "@" in e})
        self._email_model.setStringList(clean)

    # ── 호환용 메서드 ──
    def get_match_mode(self) -> str:
        return "all"

    def get_search_scope(self) -> str:
        return "all"

    def is_contains_search_enabled(self) -> bool:
        # 기본 검색은 포함 검색. '정확한 단어만' 체크 시 FTS 정확 단어 검색으로 전환한다.
        return not self.exact_word_check.isChecked()

    def set_related_keywords(self, keywords):
        # 연관검색어 기능 제거: 아무 것도 표시하지 않는다.
        return

    def set_bookmark_active(self, is_bm):
        if is_bm:
            self.bookmark_btn.setText("★")
            self.bookmark_btn.setStyleSheet(
                f"QPushButton{{background:{Colors.WARNING_BG};color:{Colors.WARNING};"
                f"border:1px solid {Colors.WARNING}40;border-radius:8px;}}"
            )
        else:
            self.bookmark_btn.setText("☆")
            self.bookmark_btn.setStyleSheet(
                f"QPushButton{{background:{Colors.BG_CARD};color:{Colors.TEXT_DIM};"
                f"border:1px solid {Colors.BORDER};border-radius:8px;}}"
                f"QPushButton:hover{{color:{Colors.WARNING};border-color:{Colors.WARNING}40;"
                f"background:{Colors.WARNING_BG};}}"
            )
