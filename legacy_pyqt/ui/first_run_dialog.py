"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[U10] 최초 실행 — Outlook 접근 동의 다이얼로그
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QRadioButton, QButtonGroup, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QCursor

from ui.theme import Colors, Fonts, Radius, APP_FULL_NAME


class FirstRunDialog(QDialog):
    """
    최초 실행 시 Outlook 접근 동의를 구하는 다이얼로그.

    Properties (accept 후 조회):
        selected_folders: List[int] — 선택된 폴더 ID 목록
        include_subfolders: bool
        range_months: int (3, 6, 12, 0=전체)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_FULL_NAME} — 시작하기")
        self.setFixedSize(520, 680)
        self.setStyleSheet(f"background-color: {Colors.BG_MAIN};")

        self._selected_folders = []
        self._include_subfolders = True
        self._range_months = 6

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 24)
        layout.setSpacing(14)

        # ── 아이콘 + 제목
        icon = QLabel("📬")
        icon.setFont(QFont("Segoe UI", 48))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("background:transparent;")
        layout.addWidget(icon)

        title = QLabel("Outlook 메일에 접근합니다")
        title.setFont(QFont("Segoe UI", Fonts.SIZE_2XL, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color:{Colors.TEXT_PRIMARY}; background:transparent;")
        layout.addWidget(title)

        desc = QLabel("이 앱은 Outlook에 저장된 메일을 읽어\n빠른 검색을 위한 로컬 인덱스를 생성합니다.")
        desc.setFont(QFont("Segoe UI", Fonts.SIZE_BASE))
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet(f"color:{Colors.TEXT_SECONDARY}; background:transparent; line-height:1.6;")
        layout.addWidget(desc)

        # ── 프라이버시 안내
        privacy = QWidget()
        privacy.setStyleSheet(f"background-color:{Colors.SUCCESS_BG}; border:1px solid {Colors.SUCCESS}30; border-radius:{Radius.MD}px;")
        p_layout = QVBoxLayout(privacy)
        p_layout.setContentsMargins(16, 12, 16, 12)
        p_layout.setSpacing(5)
        for txt in ["🔒 메일 데이터는 이 PC에만 저장됩니다",
                     "🚫 외부 서버로 전송하지 않습니다",
                     "💻 Outlook이 실행 중이어야 합니다"]:
            lbl = QLabel(txt)
            lbl.setFont(QFont("Segoe UI", Fonts.SIZE_SM))
            lbl.setStyleSheet(f"color:{Colors.SUCCESS}; background:transparent; border:none;")
            p_layout.addWidget(lbl)
        layout.addWidget(privacy)

        # ── 폴더 선택
        self._add_section_label(layout, "인덱싱 대상 폴더")
        folder_box = self._make_card()
        f_layout = QVBoxLayout(folder_box)
        f_layout.setContentsMargins(16, 10, 16, 10)
        f_layout.setSpacing(4)

        self.folder_checks = {}
        folder_items = [
            (6, "📥 받은편지함", True),
            (5, "📤 보낸편지함", True),
            (16, "📝 임시보관함", False),
            (3, "🗑 지운편지함", False),
        ]
        for fid, text, checked in folder_items:
            cb = self._make_checkbox(text, checked)
            self.folder_checks[fid] = cb
            f_layout.addWidget(cb)

        self.subfolder_check = self._make_checkbox("📂 하위 폴더 포함", True)
        f_layout.addWidget(self.subfolder_check)
        layout.addWidget(folder_box)

        # ── 인덱싱 범위
        self._add_section_label(layout, "인덱싱 범위")
        range_box = self._make_card()
        r_layout = QHBoxLayout(range_box)
        r_layout.setContentsMargins(16, 10, 16, 10)

        self.range_group = QButtonGroup(self)
        self.range_radios = {}
        for text, months, checked in [("3개월", 3, False), ("6개월", 6, True),
                                       ("1년", 12, False), ("전체", 0, False)]:
            rb = QRadioButton(text)
            rb.setChecked(checked)
            rb.setFont(QFont("Segoe UI", Fonts.SIZE_SM))
            rb.setStyleSheet(f"""
                QRadioButton {{ color:{Colors.TEXT_SECONDARY}; spacing:6px; background:transparent; border:none; }}
                QRadioButton::indicator {{ width:16px; height:16px; border:2px solid {Colors.TEXT_DIM}; border-radius:8px; background:transparent; }}
                QRadioButton::indicator:checked {{ background-color:{Colors.PRIMARY}; border-color:{Colors.PRIMARY}; }}
            """)
            self.range_group.addButton(rb, months)
            self.range_radios[months] = rb
            r_layout.addWidget(rb)
        layout.addWidget(range_box)

        layout.addStretch()

        # ── 버튼
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        later_btn = QPushButton("나중에")
        later_btn.setFixedHeight(42)
        later_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        later_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent; color:{Colors.TEXT_DIM}; border:1px solid {Colors.BORDER}; border-radius:{Radius.MD}px; padding:8px 24px; font-size:{Fonts.SIZE_BASE}px; }}
            QPushButton:hover {{ background-color:{Colors.BG_CARD_HOVER}; color:{Colors.TEXT_SECONDARY}; }}
        """)
        later_btn.clicked.connect(self.reject)
        btn_row.addWidget(later_btn)

        accept_btn = QPushButton("✅ 수락하고 인덱싱 시작")
        accept_btn.setFixedHeight(42)
        accept_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        accept_btn.setStyleSheet(f"""
            QPushButton {{ background-color:{Colors.PRIMARY}; color:#FFFFFF; border:none; border-radius:{Radius.MD}px; padding:8px 24px; font-size:{Fonts.SIZE_BASE}px; font-weight:bold; }}
            QPushButton:hover {{ background-color:{Colors.PRIMARY_HOVER}; }}
        """)
        accept_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(accept_btn, 1)

        layout.addLayout(btn_row)

    def _on_accept(self):
        self._selected_folders = [fid for fid, cb in self.folder_checks.items() if cb.isChecked()]
        self._include_subfolders = self.subfolder_check.isChecked()
        self._range_months = self.range_group.checkedId()
        self.accept()

    # ── Properties ──
    @property
    def selected_folders(self):
        return self._selected_folders

    @property
    def include_subfolders(self):
        return self._include_subfolders

    @property
    def range_months(self):
        return self._range_months

    # ── 헬퍼 ──
    def _add_section_label(self, layout, text):
        lbl = QLabel(text)
        lbl.setFont(QFont("Segoe UI", Fonts.SIZE_SM, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{Colors.TEXT_SECONDARY}; background:transparent;")
        layout.addWidget(lbl)

    def _make_card(self):
        w = QWidget()
        w.setStyleSheet(f"background-color:{Colors.BG_CARD}; border:1px solid {Colors.BORDER}; border-radius:{Radius.MD}px;")
        return w

    def _make_checkbox(self, text, checked):
        cb = QCheckBox(text)
        cb.setChecked(checked)
        cb.setFont(QFont("Segoe UI", Fonts.SIZE_SM))
        cb.setStyleSheet(f"""
            QCheckBox {{ color:{Colors.TEXT_SECONDARY}; spacing:8px; background:transparent; border:none; }}
            QCheckBox::indicator {{ width:18px; height:18px; border:2px solid {Colors.TEXT_DIM}; border-radius:4px; background:transparent; }}
            QCheckBox::indicator:checked {{ background-color:{Colors.PRIMARY}; border-color:{Colors.PRIMARY}; }}
        """)
        return cb
