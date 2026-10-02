"""
OutLook AnyFinder Ver0.9 for SESUNG Team
에러 다이얼로그 — 사용자 친화적 에러 표시
"""

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QCursor

from ui.theme import Colors, Fonts, Radius, APP_FULL_NAME


class ErrorDialog(QDialog):
    """
    사용자 친화적 에러 다이얼로그.

    사용법:
        ErrorDialog.show_error(parent, title, message, suggestion)
        ErrorDialog.show_app_error(parent, AppError_instance)
    """

    def __init__(self, title: str, message: str, suggestion: str = "",
                 icon: str = "❌", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_FULL_NAME} — 오류")
        self.setFixedSize(440, 300)
        self.setStyleSheet(f"background-color:{Colors.BG_MAIN};")
        self._build(title, message, suggestion, icon)

    def _build(self, title, message, suggestion, icon):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 20)
        layout.setSpacing(14)

        # 아이콘
        icon_label = QLabel(icon)
        icon_label.setFont(QFont("Segoe UI", 36))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("background:transparent;")
        layout.addWidget(icon_label)

        # 제목
        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", Fonts.SIZE_XL, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet(f"color:{Colors.TEXT_PRIMARY};background:transparent;")
        layout.addWidget(title_label)

        # 메시지
        msg_label = QLabel(message)
        msg_label.setFont(QFont("Segoe UI", Fonts.SIZE_BASE))
        msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg_label.setStyleSheet(f"color:{Colors.TEXT_SECONDARY};background:transparent;")
        msg_label.setWordWrap(True)
        layout.addWidget(msg_label)

        # 제안
        if suggestion:
            sug_label = QLabel(f"💡 {suggestion}")
            sug_label.setFont(QFont("Segoe UI", Fonts.SIZE_SM))
            sug_label.setStyleSheet(f"color:{Colors.ACCENT};background:{Colors.ACCENT_BG};border:1px solid {Colors.ACCENT}30;border-radius:{Radius.MD}px;padding:10px;")
            sug_label.setWordWrap(True)
            layout.addWidget(sug_label)

        layout.addStretch()

        # 확인 버튼
        ok_btn = QPushButton("확인")
        ok_btn.setFixedHeight(38)
        ok_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        ok_btn.setStyleSheet(f"QPushButton{{background:{Colors.PRIMARY};color:#FFF;border:none;border-radius:8px;padding:6px 24px;font-weight:bold;}}QPushButton:hover{{background:{Colors.PRIMARY_HOVER};}}")
        ok_btn.clicked.connect(self.accept)
        layout.addWidget(ok_btn)

    @staticmethod
    def show_error(parent, title: str, message: str, suggestion: str = "", icon: str = "❌"):
        dialog = ErrorDialog(title, message, suggestion, icon, parent)
        dialog.exec()

    @staticmethod
    def show_app_error(parent, error):
        """AppError 인스턴스로 표시"""
        from core.error_handler import AppError
        if isinstance(error, AppError):
            dialog = ErrorDialog(error.title, error.message, error.suggestion, "⚠", parent)
        else:
            dialog = ErrorDialog("오류 발생", str(error), "앱을 재시작해 보세요.", "❌", parent)
        dialog.exec()

    @staticmethod
    def show_outlook_error(parent):
        ErrorDialog.show_error(
            parent,
            "Outlook 연결 실패",
            "Microsoft Outlook이 실행되고 있지 않거나\n연결할 수 없습니다.",
            "Outlook을 실행한 후 다시 시도해 주세요.\n데모 모드로 계속 사용할 수 있습니다.",
            "📧"
        )

    @staticmethod
    def show_no_results(parent, query: str):
        suggestions = []
        if query:
            suggestions.append(f"• 검색어를 줄여보세요: '{query.split()[0]}'" if ' ' in query else "")
            suggestions.append("• 필터를 초기화해 보세요")
            suggestions.append("• 다른 키워드로 시도해 보세요")
        sug = "\n".join([s for s in suggestions if s])

        ErrorDialog.show_error(
            parent,
            "검색 결과 없음",
            f'"{query}"에 대한 검색 결과가 없습니다.',
            sug if sug else "다른 검색어로 시도해 보세요.",
            "🔍"
        )
