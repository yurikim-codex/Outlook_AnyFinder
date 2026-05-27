"""
OutLook AnyFinder Ver0.9 for SESUNG Team
테마 & 디자인 토큰 시스템
"""

APP_NAME = "OutLook AnyFinder"
APP_VERSION = "Ver0.9"
APP_SUBTITLE = "for SESUNG Team"
APP_FULL_NAME = f"{APP_NAME} {APP_VERSION} {APP_SUBTITLE}"


class Colors:
    # 배경
    BG_MAIN = "#0B0F19"
    BG_SIDEBAR = "#0F1420"
    BG_CARD = "#141A2A"
    BG_CARD_HOVER = "#1A2236"
    BG_INPUT = "#111827"
    BG_ELEVATED = "#1E2740"

    # 텍스트
    TEXT_PRIMARY = "#F1F5F9"
    TEXT_SECONDARY = "#94A3B8"
    TEXT_DIM = "#64748B"
    TEXT_MUTED = "#475569"

    # 액센트
    PRIMARY = "#6366F1"
    PRIMARY_HOVER = "#818CF8"
    PRIMARY_BG = "#6366F120"
    ACCENT = "#38BDF8"
    ACCENT_BG = "#38BDF815"

    # 상태
    SUCCESS = "#10B981"
    SUCCESS_BG = "#10B98120"
    WARNING = "#F59E0B"
    WARNING_BG = "#F59E0B20"
    DANGER = "#EF4444"
    DANGER_BG = "#EF444420"

    # 보더
    BORDER = "#1E293B"
    BORDER_LIGHT = "#334155"
    BORDER_FOCUS = "#6366F1"

    # 뱃지
    BADGE_INBOX = "#6366F1"
    BADGE_SENT = "#10B981"
    BADGE_DRAFT = "#F59E0B"
    BADGE_TRASH = "#EF4444"
    BADGE_FOLDER = "#8B5CF6"

    # 첨부파일 형식
    ATT_XLSX = "#10B981"
    ATT_PDF = "#EF4444"
    ATT_DOCX = "#3B82F6"
    ATT_PPTX = "#F59E0B"
    ATT_IMG = "#EC4899"
    ATT_OTHER = "#64748B"

    # 하이라이트
    HIGHLIGHT_BG = "#F97316"
    HIGHLIGHT_TEXT = "#FFFFFF"


class Fonts:
    FAMILY = "'Segoe UI', 'Malgun Gothic', sans-serif"
    MONO = "'Consolas', 'D2Coding', monospace"
    SIZE_XS = 10
    SIZE_SM = 11
    SIZE_BASE = 13
    SIZE_LG = 15
    SIZE_XL = 18
    SIZE_2XL = 22
    SIZE_3XL = 28


class Radius:
    SM = 6
    MD = 10
    LG = 14
    XL = 18


def global_stylesheet():
    return f"""
        QMainWindow {{ background-color: {Colors.BG_MAIN}; }}
        QWidget {{ color: {Colors.TEXT_PRIMARY}; font-family: {Fonts.FAMILY}; font-size: {Fonts.SIZE_BASE}px; }}
        QScrollArea {{ border: none; background: transparent; }}
        QScrollBar:vertical {{ background: transparent; width: 6px; margin: 4px 0; }}
        QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 3px; min-height: 30px; }}
        QScrollBar::handle:vertical:hover {{ background: {Colors.TEXT_DIM}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QToolTip {{ background-color: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY}; border: 1px solid {Colors.BORDER_LIGHT}; border-radius: {Radius.SM}px; padding: 6px 10px; font-size: {Fonts.SIZE_SM}px; }}
    """
