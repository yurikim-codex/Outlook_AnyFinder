"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[U07] 메일 상세 미리보기 패널
"""

import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFrame, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QCursor

from ui.theme import Colors, Fonts, Radius
from data.models import SearchResult
from utils.date_utils import format_display_date


class MailPreview(QWidget):
    """선택된 메일의 상세 미리보기"""
    open_in_outlook = pyqtSignal(str)  # entry_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_entry_id = ""
        self.setStyleSheet(f"background-color:{Colors.BG_CARD};border:1px solid {Colors.BORDER};border-radius:{Radius.LG}px;")
        self._build()
        self._show_placeholder()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(10)

        # 제목
        self.subject_label = QLabel("")
        self.subject_label.setFont(QFont("Segoe UI", Fonts.SIZE_XL, QFont.Weight.Bold))
        self.subject_label.setStyleSheet(f"color:{Colors.TEXT_PRIMARY};background:transparent;border:none;")
        self.subject_label.setWordWrap(True)
        layout.addWidget(self.subject_label)

        # 구분선
        layout.addWidget(self._sep())

        # 메타 정보
        self.meta_from = QLabel("")
        self.meta_to = QLabel("")
        self.meta_date = QLabel("")
        self.meta_att = QLabel("")

        for lbl in [self.meta_from, self.meta_to, self.meta_date, self.meta_att]:
            lbl.setFont(QFont("Segoe UI", Fonts.SIZE_SM))
            lbl.setStyleSheet(f"color:{Colors.TEXT_SECONDARY};background:transparent;border:none;")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setWordWrap(True)
            layout.addWidget(lbl)

        layout.addWidget(self._sep())

        # 본문
        self.body_edit = QTextEdit()
        self.body_edit.setReadOnly(True)
        self.body_edit.setFont(QFont("Segoe UI", Fonts.SIZE_BASE))
        self.body_edit.setStyleSheet(f"""
            QTextEdit{{background:transparent;color:{Colors.TEXT_SECONDARY};border:none;padding:0;}}
        """)
        layout.addWidget(self.body_edit, 1)

        # 하단 액션
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self.btn_outlook = self._action_btn("📂 Outlook에서 열기", Colors.PRIMARY)
        self.btn_outlook.clicked.connect(lambda: self.open_in_outlook.emit(self.current_entry_id))
        action_row.addWidget(self.btn_outlook)

        self.btn_reply = self._action_btn("↩ 답장", Colors.TEXT_DIM)
        action_row.addWidget(self.btn_reply)

        self.btn_forward = self._action_btn("↗ 전달", Colors.TEXT_DIM)
        action_row.addWidget(self.btn_forward)

        action_row.addStretch()
        layout.addLayout(action_row)

    def show_result(self, result: SearchResult):
        """SearchResult로 미리보기 업데이트"""
        e = result.email
        self.current_entry_id = e.entry_id

        self.subject_label.setText(e.subject or "(제목 없음)")

        lbl_style = f'style="color:{Colors.TEXT_DIM}"'
        self.meta_from.setText(
            f'<b {lbl_style}>보낸사람</b>  {e.sender_name} &lt;{e.sender_email}&gt;'
        )

        to_text = e.recipients or ""
        if e.cc:
            to_text += f'  <span style="color:{Colors.TEXT_DIM}">CC: {e.cc}</span>'
        self.meta_to.setText(f'<b {lbl_style}>받는사람</b>  {to_text}')

        self.meta_date.setText(
            f'<b {lbl_style}>날짜</b>  {format_display_date(e.received_at)} ({e.received_at[:10]})'
        )

        if e.has_attachments and e.attachment_names:
            att_parts = []
            ext_colors = {".xlsx": Colors.ATT_XLSX, ".pdf": Colors.ATT_PDF,
                          ".docx": Colors.ATT_DOCX, ".pptx": Colors.ATT_PPTX}
            for name in e.attachment_names.split(", "):
                ext = os.path.splitext(name)[1].lower()
                c = ext_colors.get(ext, Colors.ATT_OTHER)
                att_parts.append(f'<span style="color:{c}">{name}</span>')
            self.meta_att.setText(f'<b {lbl_style}>첨부파일</b>  📎 {", ".join(att_parts)}')
            self.meta_att.show()
        else:
            self.meta_att.hide()

        self.body_edit.setPlainText(e.body_text or "(본문 없음)")

        self.btn_outlook.setEnabled(True)
        self.btn_reply.setEnabled(True)
        self.btn_forward.setEnabled(True)

    def _show_placeholder(self):
        self.subject_label.setText("📧 메일을 선택하세요")
        self.meta_from.setText("")
        self.meta_to.setText("")
        self.meta_date.setText("")
        self.meta_att.hide()
        self.body_edit.setPlainText("")
        self.btn_outlook.setEnabled(False)
        self.btn_reply.setEnabled(False)
        self.btn_forward.setEnabled(False)

    def _sep(self):
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet(f"background:{Colors.BORDER};border:none;max-height:1px;")
        return f

    def _action_btn(self, text, color):
        btn = QPushButton(text)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setFixedHeight(32)
        btn.setStyleSheet(f"""
            QPushButton{{background:transparent;color:{color};border:1px solid {color}40;border-radius:8px;padding:4px 14px;font-size:{Fonts.SIZE_SM}px;}}
            QPushButton:hover{{background:{color}15;}}
            QPushButton:disabled{{color:{Colors.TEXT_MUTED};border-color:{Colors.BORDER};}}
        """)
        return btn
