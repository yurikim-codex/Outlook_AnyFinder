"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[U11] 수동 동기화 대상 폴더 선택 다이얼로그
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QWidget, QMessageBox, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QCursor

from ui.theme import Colors, Fonts, Radius, APP_FULL_NAME


class SyncFolderDialog(QDialog):
    """
    '지금 동기화' 클릭 시 표시되는 동기화 대상 폴더 선택 창.

    Properties (accept 후 조회):
        selected_folders: List[int]
        include_subfolders: bool
    """

    FOLDER_ITEMS = [
        (6, "📥 받은편지함", "수신된 메일을 동기화합니다."),
        (5, "📤 보낸편지함", "발송한 메일을 동기화합니다."),
        (16, "📝 임시보관함", "작성 중인 임시 메일을 포함합니다."),
        (3, "🗑 지운편지함", "삭제/이동된 메일 상태 확인에 사용합니다."),
    ]

    def __init__(self, selected_folders=None, include_subfolders=True, range_months=6, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_FULL_NAME} — 동기화 대상 선택")
        self.setFixedSize(540, 620)
        self.setStyleSheet(f"background-color: {Colors.BG_MAIN};")

        self._initial_selected = set(selected_folders or [6, 5])
        self._initial_include_subfolders = include_subfolders
        self._initial_range_months = range_months
        self._selected_folders = []
        self._include_subfolders = True
        self._range_months = range_months
        self.folder_checks = {}

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 28, 34, 24)
        layout.setSpacing(14)

        icon = QLabel("🔄")
        icon.setFont(QFont("Segoe UI", 42))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("background:transparent;")
        layout.addWidget(icon)

        title = QLabel("동기화할 Outlook 폴더를 선택하세요")
        title.setFont(QFont("Segoe UI", Fonts.SIZE_XL, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color:{Colors.TEXT_PRIMARY}; background:transparent;")
        layout.addWidget(title)

        desc = QLabel("선택한 폴더만 Outlook과 비교한 뒤 변경 사항을 동기화합니다.")
        desc.setFont(QFont("Segoe UI", Fonts.SIZE_SM))
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color:{Colors.TEXT_SECONDARY}; background:transparent;")
        layout.addWidget(desc)

        folder_box = self._make_card()
        f_layout = QVBoxLayout(folder_box)
        f_layout.setContentsMargins(16, 12, 16, 12)
        f_layout.setSpacing(10)

        for fid, text, help_text in self.FOLDER_ITEMS:
            row = QWidget()
            row.setStyleSheet("background:transparent;border:none;")
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(2)

            cb = self._make_checkbox(text, fid in self._initial_selected)
            self.folder_checks[fid] = cb
            row_layout.addWidget(cb)

            help_lbl = QLabel(f"   {help_text}")
            help_lbl.setFont(QFont("Segoe UI", Fonts.SIZE_XS))
            help_lbl.setStyleSheet(f"color:{Colors.TEXT_MUTED}; background:transparent; border:none;")
            row_layout.addWidget(help_lbl)
            f_layout.addWidget(row)

        layout.addWidget(folder_box)

        option_box = self._make_card()
        o_layout = QVBoxLayout(option_box)
        o_layout.setContentsMargins(16, 12, 16, 12)
        self.subfolder_check = self._make_checkbox("📂 선택한 폴더의 하위 폴더 포함", self._initial_include_subfolders)
        o_layout.addWidget(self.subfolder_check)
        note = QLabel("하위 폴더가 많으면 비교 시간이 길어질 수 있습니다.")
        note.setFont(QFont("Segoe UI", Fonts.SIZE_XS))
        note.setStyleSheet(f"color:{Colors.TEXT_MUTED}; background:transparent; border:none;")
        o_layout.addWidget(note)
        layout.addWidget(option_box)

        range_box = self._make_card()
        r_layout = QVBoxLayout(range_box)
        r_layout.setContentsMargins(16, 12, 16, 12)
        r_layout.setSpacing(8)
        range_title = QLabel("🗓 동기화할 인덱싱 범위")
        range_title.setFont(QFont("Segoe UI", Fonts.SIZE_SM, QFont.Weight.Bold))
        range_title.setStyleSheet(f"color:{Colors.TEXT_SECONDARY}; background:transparent; border:none;")
        r_layout.addWidget(range_title)

        radio_row = QHBoxLayout()
        self.range_group = QButtonGroup(self)
        self.range_radios = {}
        for text, months in [("3개월", 3), ("6개월", 6), ("1년", 12), ("전체", 0)]:
            rb = QRadioButton(text)
            rb.setChecked(months == self._initial_range_months)
            rb.setFont(QFont("Segoe UI", Fonts.SIZE_SM))
            rb.setStyleSheet(f"""
                QRadioButton {{ color:{Colors.TEXT_SECONDARY}; spacing:6px; background:transparent; border:none; }}
                QRadioButton::indicator {{ width:15px; height:15px; border:2px solid {Colors.TEXT_DIM}; border-radius:8px; background:transparent; }}
                QRadioButton::indicator:checked {{ background-color:{Colors.PRIMARY}; border-color:{Colors.PRIMARY}; }}
            """)
            self.range_group.addButton(rb, months)
            self.range_radios[months] = rb
            radio_row.addWidget(rb)
        r_layout.addLayout(radio_row)
        layout.addWidget(range_box)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        cancel_btn = QPushButton("취소")
        cancel_btn.setFixedHeight(42)
        cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent; color:{Colors.TEXT_DIM}; border:1px solid {Colors.BORDER}; border-radius:{Radius.MD}px; padding:8px 24px; font-size:{Fonts.SIZE_BASE}px; }}
            QPushButton:hover {{ background-color:{Colors.BG_CARD_HOVER}; color:{Colors.TEXT_SECONDARY}; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        sync_btn = QPushButton("🔄 동기화")
        sync_btn.setFixedHeight(42)
        sync_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        sync_btn.setStyleSheet(f"""
            QPushButton {{ background-color:{Colors.PRIMARY}; color:#FFFFFF; border:none; border-radius:{Radius.MD}px; padding:8px 24px; font-size:{Fonts.SIZE_BASE}px; font-weight:bold; }}
            QPushButton:hover {{ background-color:{Colors.PRIMARY_HOVER}; }}
        """)
        sync_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(sync_btn, 1)

        layout.addLayout(btn_row)

    def _on_accept(self):
        self._selected_folders = [fid for fid, cb in self.folder_checks.items() if cb.isChecked()]
        if not self._selected_folders:
            QMessageBox.warning(
                self,
                "폴더 선택 필요",
                "동기화할 폴더를 하나 이상 선택해 주세요."
            )
            return
        self._include_subfolders = self.subfolder_check.isChecked()
        self._range_months = self.range_group.checkedId()
        self.accept()

    @property
    def selected_folders(self):
        return self._selected_folders

    @property
    def include_subfolders(self):
        return self._include_subfolders

    @property
    def range_months(self):
        return self._range_months

    @classmethod
    def folder_names(cls, folder_ids):
        names = {fid: text for fid, text, _ in cls.FOLDER_ITEMS}
        return [names.get(fid, f"폴더 {fid}") for fid in folder_ids]

    def _make_card(self):
        w = QWidget()
        w.setStyleSheet(f"background-color:{Colors.BG_CARD}; border:1px solid {Colors.BORDER}; border-radius:{Radius.MD}px;")
        return w

    def _make_checkbox(self, text, checked):
        cb = QCheckBox(text)
        cb.setChecked(checked)
        cb.setFont(QFont("Segoe UI", Fonts.SIZE_SM, QFont.Weight.Bold))
        cb.setStyleSheet(f"""
            QCheckBox {{ color:{Colors.TEXT_SECONDARY}; spacing:8px; background:transparent; border:none; }}
            QCheckBox::indicator {{ width:18px; height:18px; border:2px solid {Colors.TEXT_DIM}; border-radius:4px; background:transparent; }}
            QCheckBox::indicator:checked {{ background-color:{Colors.PRIMARY}; border-color:{Colors.PRIMARY}; }}
        """)
        return cb
