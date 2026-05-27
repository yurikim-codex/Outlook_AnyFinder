"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[U06] 메일 결과 카드 (v3)
- 날짜: "0000년 00월 00일" 형식 + 줄바꿈 후 내용
- 사각 라운드 외곽선
- 첨부파일 확장자 아이콘
- 검색어와 동일한 첨부파일명 발견 시 형광 점멸
"""

import os
import re
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPropertyAnimation, QVariant
from PyQt6.QtGui import QFont, QCursor, QColor

from ui.theme import Colors, Fonts, Radius
from data.models import SearchResult


# 확장자별 이모지 아이콘 매핑
EXT_ICONS = {
    ".xlsx": "📊", ".xls": "📊",
    ".pdf": "📕",
    ".docx": "📘", ".doc": "📘",
    ".pptx": "📙", ".ppt": "📙",
    ".jpg": "🖼", ".jpeg": "🖼", ".png": "🖼", ".gif": "🖼", ".bmp": "🖼",
    ".txt": "📄", ".md": "📄",
    ".zip": "📦", ".rar": "📦", ".7z": "📦",
    ".msg": "✉️", ".eml": "✉️",
    ".csv": "📋",
    ".html": "🌐", ".htm": "🌐",
}


def _format_date_kr(date_str: str) -> str:
    """날짜를 '0000년 00월 00일 00:00' 형식으로 변환"""
    if not date_str or len(date_str) < 10:
        return date_str
    try:
        # "2026-05-27 14:30:00" → "2026년 05월 27일 14:30"
        parts = date_str[:10].split("-")
        if len(parts) == 3:
            time_part = date_str[11:16] if len(date_str) >= 16 else ""
            return f"{parts[0]}년 {parts[1]}월 {parts[2]}일 {time_part}".strip()
    except Exception:
        pass
    return date_str[:16]


def _get_ext_icon(ext: str) -> str:
    """확장자에 맞는 아이콘 반환"""
    return EXT_ICONS.get(ext.lower(), "📎")


def _get_ext_color(ext: str) -> str:
    """확장자에 맞는 색상 (동적 해시 기반)"""
    preset = {
        ".xlsx": "#10B981", ".xls": "#10B981",
        ".pdf": "#EF4444",
        ".docx": "#3B82F6", ".doc": "#3B82F6",
        ".pptx": "#F59E0B", ".ppt": "#F59E0B",
        ".jpg": "#EC4899", ".jpeg": "#EC4899", ".png": "#EC4899",
        ".csv": "#8B5CF6",
        ".zip": "#64748B", ".rar": "#64748B",
        ".txt": "#94A3B8", ".md": "#94A3B8",
    }
    if ext.lower() in preset:
        return preset[ext.lower()]
    # 동적 색상: 확장자 해시 기반
    h = hash(ext) % 360
    return f"hsl({h}, 65%, 55%)"


class MailCard(QWidget):
    clicked = pyqtSignal(object)

    def __init__(self, result: SearchResult, search_term: str = "", parent=None):
        super().__init__(parent)
        self.result = result
        self.search_term = search_term
        self._selected = False
        self._blink_labels = []  # 점멸 대상 라벨들
        self._blink_state = False
        self._blink_timer = None
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMinimumHeight(80)
        self.setMaximumHeight(140)
        self._build()
        self._apply_style()
        self._start_blink_if_needed()

    def _build(self):
        e = self.result.email
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(3)

        # ── Row 1: 날짜 "0000년 00월 00일 00:00" + 줄바꿈 역할
        r1 = QHBoxLayout()
        r1.setSpacing(6)

        # ★ 날짜: "0000년 00월 00일 00:00"
        date_kr = _format_date_kr(e.received_at)
        date_lbl = QLabel(date_kr)
        date_lbl.setFont(QFont("Segoe UI", Fonts.SIZE_XS, QFont.Weight.Bold))
        date_lbl.setStyleSheet(f"color:{Colors.ACCENT};background:transparent;border:none;")
        date_lbl.setFixedHeight(16)
        r1.addWidget(date_lbl)

        # 읽지 않음
        if not e.is_read:
            dot = QLabel("●")
            dot.setFixedWidth(10)
            dot.setStyleSheet(f"color:{Colors.ACCENT};font-size:8px;background:transparent;border:none;")
            r1.addWidget(dot)

        # 중요도
        if e.importance == 2:
            r1.addWidget(self._tiny("❗", 14))

        r1.addStretch()

        # 폴더 뱃지
        fc_map = {"받은편지함": Colors.BADGE_INBOX, "보낸편지함": Colors.BADGE_SENT,
                   "임시보관함": Colors.BADGE_DRAFT, "지운편지함": Colors.BADGE_TRASH}
        fc = fc_map.get(e.folder_name, Colors.BADGE_FOLDER)
        badge = QLabel(e.folder_name)
        badge.setFont(QFont("Segoe UI", 9))
        badge.setStyleSheet(f"background:{fc}25;color:{fc};border:1px solid {fc}40;border-radius:3px;padding:0px 5px;")
        badge.setFixedHeight(16)
        r1.addWidget(badge)

        layout.addLayout(r1)

        # ── Row 2: 제목 (날짜 다음 줄)
        subj_text = self._highlight_text(e.subject or "(제목 없음)")
        subj = QLabel(subj_text)
        subj.setFont(QFont("Segoe UI", Fonts.SIZE_SM, QFont.Weight.Bold))
        subj.setStyleSheet(f"color:{Colors.TEXT_PRIMARY};background:transparent;border:none;")
        subj.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(subj)

        # ── Row 3: 발신자 → 수신자
        sender_txt = f"👤 {e.sender_name}"
        if e.recipients:
            sender_txt += f" → {e.recipients}"
        sl = QLabel(sender_txt)
        sl.setFont(QFont("Segoe UI", Fonts.SIZE_XS))
        sl.setStyleSheet(f"color:{Colors.TEXT_SECONDARY};background:transparent;border:none;")
        layout.addWidget(sl)

        # ── Row 4: 첨부파일 (확장자 아이콘 + 검색어 매칭 시 점멸)
        if e.has_attachments and e.attachment_names:
            r4 = QHBoxLayout()
            r4.setSpacing(3)
            for name in e.attachment_names.split(", ")[:4]:
                ext = os.path.splitext(name)[1].lower()
                icon = _get_ext_icon(ext)
                color = _get_ext_color(ext)

                al = QLabel(f"{icon} {name}")
                al.setFont(QFont("Segoe UI", 9))
                al.setStyleSheet(f"background:{color}12;color:{color};border:1px solid {color}30;border-radius:3px;padding:0px 4px;")
                al.setFixedHeight(16)

                # ★ 검색어와 첨부파일명 매칭 시 점멸 대상 등록
                if self._matches_search(name):
                    self._blink_labels.append((al, color))

                r4.addWidget(al)
            r4.addStretch()
            layout.addLayout(r4)

        # ── Row 5: snippet + 점수
        r5 = QHBoxLayout()
        snippet_src = self.result.body_snippet or e.body_text[:90]
        snippet = snippet_src.replace("\n", " ").strip()
        if len(snippet) > 90:
            snippet = snippet[:90] + "..."
        if not self.result.body_snippet:
            snippet = self._highlight_text(snippet)
        sn = QLabel(snippet)
        sn.setFont(QFont("Segoe UI", Fonts.SIZE_XS))
        sn.setStyleSheet(f"color:{Colors.TEXT_DIM};background:transparent;border:none;")
        sn.setTextFormat(Qt.TextFormat.RichText)
        sn.setWordWrap(True)
        r5.addWidget(sn, 1)

        if self.result.rank_score > 0:
            sc = self.result.rank_score
            sc_c = Colors.SUCCESS if sc > 5 else (Colors.WARNING if sc > 2 else Colors.TEXT_DIM)
            r5.addWidget(self._score_label(sc, sc_c))
        layout.addLayout(r5)

    def _matches_search(self, filename: str) -> bool:
        """첨부파일명이 검색어와 매칭되는지"""
        if not self.search_term:
            return False
        name_lower = filename.lower()
        for term in self.search_term.split():
            if term and len(term) >= 2 and term.lower() in name_lower:
                return True
        return False

    def _start_blink_if_needed(self):
        """검색어 매칭 첨부파일이 있으면 점멸 시작"""
        if not self._blink_labels:
            return
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(1000)  # 1초 간격
        self._blink_timer.timeout.connect(self._do_blink)
        self._blink_timer.start()

    def _do_blink(self):
        """형광색 점멸"""
        self._blink_state = not self._blink_state
        for lbl, color in self._blink_labels:
            if self._blink_state:
                lbl.setStyleSheet(f"background:#FBBF24;color:#000;border:2px solid #F59E0B;border-radius:3px;padding:0px 4px;font-weight:bold;")
            else:
                lbl.setStyleSheet(f"background:{color}12;color:{color};border:1px solid {color}30;border-radius:3px;padding:0px 4px;")

    def _highlight_text(self, text):
        if not self.search_term or not text:
            return text
        for term in self.search_term.split():
            if term and len(term) >= 2 and term.lower() in text.lower():
                pattern = re.compile(re.escape(term), re.IGNORECASE)
                text = pattern.sub(
                    lambda m: f'<span style="background:{Colors.HIGHLIGHT_BG};color:{Colors.HIGHLIGHT_TEXT};padding:0 2px;border-radius:2px;">{m.group()}</span>',
                    text
                )
        return text

    def _tiny(self, text, w):
        l = QLabel(text); l.setFixedWidth(w); l.setStyleSheet("background:transparent;border:none;"); return l

    def _score_label(self, sc, color):
        l = QLabel(f"★{sc:.1f}"); l.setFont(QFont("Segoe UI",9,QFont.Weight.Bold))
        l.setStyleSheet(f"color:{color};background:transparent;border:none;"); l.setFixedWidth(40)
        l.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTop); return l

    def set_selected(self, selected):
        self._selected = selected
        self._apply_style()

    def _apply_style(self):
        # ★ 사각 라운드 외곽선 추가
        if self._selected:
            self.setStyleSheet(f"MailCard{{background:{Colors.PRIMARY_BG};border:2px solid {Colors.PRIMARY};border-radius:{Radius.MD}px;}}")
        else:
            self.setStyleSheet(f"MailCard{{background:{Colors.BG_CARD};border:1px solid {Colors.BORDER_LIGHT};border-radius:{Radius.MD}px;}}MailCard:hover{{background:{Colors.BG_CARD_HOVER};border:1px solid {Colors.PRIMARY}40;}}")

    def mousePressEvent(self, event):
        self.clicked.emit(self.result)
        super().mousePressEvent(event)
