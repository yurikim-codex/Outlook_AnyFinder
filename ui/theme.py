"""
OutLook AnyFinder Ver0.9.1.1 for SESUNG Team
테마 & 디자인 토큰 시스템

설정에서 선택 가능한 UI 테마:
  - dark  : 모던 다크 / Slack-like sidebar / Outlook-style content cards
  - light : 모던 화이트 / 부드러운 계층 / 명확한 선택 상태
"""

APP_NAME = "OutLook AnyFinder"
APP_VERSION = "Ver0.9.1"
APP_SUBTITLE = "for SESUNG Team"
APP_FULL_NAME = f"{APP_NAME} {APP_VERSION} {APP_SUBTITLE}"


THEMES = {
    "dark": {
        # 배경
        "BG_MAIN": "#0F172A",
        "BG_SIDEBAR": "#111827",
        "BG_CARD": "#1E293B",
        "BG_CARD_HOVER": "#273449",
        "BG_INPUT": "#0B1220",
        "BG_ELEVATED": "#273449",

        # 텍스트
        "TEXT_PRIMARY": "#F8FAFC",
        "TEXT_SECONDARY": "#CBD5E1",
        "TEXT_DIM": "#94A3B8",
        "TEXT_MUTED": "#64748B",

        # 액센트 - Outlook/Slack 느낌의 블루/퍼플
        "PRIMARY": "#2563EB",
        "PRIMARY_HOVER": "#60A5FA",
        "PRIMARY_BG": "#2563EB22",
        "ACCENT": "#8B5CF6",
        "ACCENT_BG": "#8B5CF61A",

        # 상태
        "SUCCESS": "#22C55E",
        "SUCCESS_BG": "#22C55E1F",
        "WARNING": "#F59E0B",
        "WARNING_BG": "#F59E0B20",
        "DANGER": "#EF4444",
        "DANGER_BG": "#EF444420",

        # 보더
        "BORDER": "#334155",
        "BORDER_LIGHT": "#475569",
        "BORDER_FOCUS": "#2563EB",

        # 뱃지
        "BADGE_INBOX": "#2563EB",
        "BADGE_SENT": "#22C55E",
        "BADGE_DRAFT": "#F59E0B",
        "BADGE_TRASH": "#EF4444",
        "BADGE_FOLDER": "#8B5CF6",

        # 첨부파일 형식
        "ATT_XLSX": "#22C55E",
        "ATT_PDF": "#EF4444",
        "ATT_DOCX": "#3B82F6",
        "ATT_PPTX": "#F59E0B",
        "ATT_IMG": "#EC4899",
        "ATT_OTHER": "#94A3B8",

        # 하이라이트
        "HIGHLIGHT_BG": "#F97316",
        "HIGHLIGHT_TEXT": "#FFFFFF",
    },
    "light": {
        # Mac OS / Linear 스타일 화이트 테마
        # 배경
        "BG_MAIN": "#F5F5F7",
        "BG_SIDEBAR": "#FBFBFD",
        "BG_CARD": "#FFFFFF",
        "BG_CARD_HOVER": "#F2F2F7",
        "BG_INPUT": "#FFFFFF",
        "BG_ELEVATED": "#FFFFFF",

        # 텍스트
        "TEXT_PRIMARY": "#1D1D1F",
        "TEXT_SECONDARY": "#3A3A3C",
        "TEXT_DIM": "#6E6E73",
        "TEXT_MUTED": "#9A9AA0",

        # 액센트 - macOS blue + Linear purple
        "PRIMARY": "#007AFF",
        "PRIMARY_HOVER": "#0A84FF",
        "PRIMARY_BG": "#E8F2FF",
        "ACCENT": "#5E5CE6",
        "ACCENT_BG": "#F0EFFF",

        # 상태
        "SUCCESS": "#30D158",
        "SUCCESS_BG": "#E8F8EE",
        "WARNING": "#FF9F0A",
        "WARNING_BG": "#FFF4E0",
        "DANGER": "#FF453A",
        "DANGER_BG": "#FFECEB",

        # 보더
        "BORDER": "#E5E5EA",
        "BORDER_LIGHT": "#C7C7CC",
        "BORDER_FOCUS": "#007AFF",

        # 뱃지
        "BADGE_INBOX": "#007AFF",
        "BADGE_SENT": "#30D158",
        "BADGE_DRAFT": "#FF9F0A",
        "BADGE_TRASH": "#FF453A",
        "BADGE_FOLDER": "#5E5CE6",

        # 첨부파일 형식
        "ATT_XLSX": "#30D158",
        "ATT_PDF": "#FF453A",
        "ATT_DOCX": "#007AFF",
        "ATT_PPTX": "#FF9F0A",
        "ATT_IMG": "#FF2D55",
        "ATT_OTHER": "#6E6E73",

        # 하이라이트
        "HIGHLIGHT_BG": "#FFE7C2",
        "HIGHLIGHT_TEXT": "#8A4B00",
    },
}


class Colors:
    # 기본값은 dark. apply_theme()로 런타임 변경 가능.
    BG_MAIN = THEMES["dark"]["BG_MAIN"]
    BG_SIDEBAR = THEMES["dark"]["BG_SIDEBAR"]
    BG_CARD = THEMES["dark"]["BG_CARD"]
    BG_CARD_HOVER = THEMES["dark"]["BG_CARD_HOVER"]
    BG_INPUT = THEMES["dark"]["BG_INPUT"]
    BG_ELEVATED = THEMES["dark"]["BG_ELEVATED"]

    TEXT_PRIMARY = THEMES["dark"]["TEXT_PRIMARY"]
    TEXT_SECONDARY = THEMES["dark"]["TEXT_SECONDARY"]
    TEXT_DIM = THEMES["dark"]["TEXT_DIM"]
    TEXT_MUTED = THEMES["dark"]["TEXT_MUTED"]

    PRIMARY = THEMES["dark"]["PRIMARY"]
    PRIMARY_HOVER = THEMES["dark"]["PRIMARY_HOVER"]
    PRIMARY_BG = THEMES["dark"]["PRIMARY_BG"]
    ACCENT = THEMES["dark"]["ACCENT"]
    ACCENT_BG = THEMES["dark"]["ACCENT_BG"]

    SUCCESS = THEMES["dark"]["SUCCESS"]
    SUCCESS_BG = THEMES["dark"]["SUCCESS_BG"]
    WARNING = THEMES["dark"]["WARNING"]
    WARNING_BG = THEMES["dark"]["WARNING_BG"]
    DANGER = THEMES["dark"]["DANGER"]
    DANGER_BG = THEMES["dark"]["DANGER_BG"]

    BORDER = THEMES["dark"]["BORDER"]
    BORDER_LIGHT = THEMES["dark"]["BORDER_LIGHT"]
    BORDER_FOCUS = THEMES["dark"]["BORDER_FOCUS"]

    BADGE_INBOX = THEMES["dark"]["BADGE_INBOX"]
    BADGE_SENT = THEMES["dark"]["BADGE_SENT"]
    BADGE_DRAFT = THEMES["dark"]["BADGE_DRAFT"]
    BADGE_TRASH = THEMES["dark"]["BADGE_TRASH"]
    BADGE_FOLDER = THEMES["dark"]["BADGE_FOLDER"]

    ATT_XLSX = THEMES["dark"]["ATT_XLSX"]
    ATT_PDF = THEMES["dark"]["ATT_PDF"]
    ATT_DOCX = THEMES["dark"]["ATT_DOCX"]
    ATT_PPTX = THEMES["dark"]["ATT_PPTX"]
    ATT_IMG = THEMES["dark"]["ATT_IMG"]
    ATT_OTHER = THEMES["dark"]["ATT_OTHER"]

    HIGHLIGHT_BG = THEMES["dark"]["HIGHLIGHT_BG"]
    HIGHLIGHT_TEXT = THEMES["dark"]["HIGHLIGHT_TEXT"]


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
    SM = 8
    MD = 12
    LG = 16
    XL = 22


def apply_theme(theme_name: str = "dark") -> str:
    """Colors 클래스 토큰을 선택한 테마로 갱신한다."""
    key = theme_name if theme_name in THEMES else "dark"
    for name, value in THEMES[key].items():
        setattr(Colors, name, value)
    return key


def global_stylesheet():
    return f"""
        QMainWindow {{ background-color: {Colors.BG_MAIN}; }}
        QWidget {{ color: {Colors.TEXT_PRIMARY}; font-family: {Fonts.FAMILY}; font-size: {Fonts.SIZE_BASE}px; }}
        QScrollArea {{ border: none; background: transparent; }}
        QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 0; }}
        QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 4px; min-height: 34px; }}
        QScrollBar::handle:vertical:hover {{ background: {Colors.TEXT_DIM}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QPushButton {{ border-radius: {Radius.SM}px; }}
        QPushButton:hover {{ border-color: {Colors.BORDER_LIGHT}; }}
        QToolTip {{ background-color: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY}; border: 1px solid {Colors.BORDER_LIGHT}; border-radius: {Radius.SM}px; padding: 6px 10px; font-size: {Fonts.SIZE_SM}px; }}
    """
