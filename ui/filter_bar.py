"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[U04] 필터 바 (v2 — 동적 확장자 필터 + '첨부 없음' + 자동 색상)
"""

import hashlib
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QComboBox, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QCursor, QAction, QColor

from ui.theme import Colors, Fonts, Radius


# 동적 확장자 색상 생성
def _ext_color(ext: str) -> str:
    """확장자에 따른 색상 (프리셋 + 해시 기반 동적)"""
    preset = {
        ".xlsx": "#10B981", ".xls": "#10B981",
        ".pdf": "#EF4444",
        ".docx": "#3B82F6", ".doc": "#3B82F6",
        ".pptx": "#F59E0B", ".ppt": "#F59E0B",
        ".jpg": "#EC4899", ".jpeg": "#EC4899", ".png": "#EC4899",
        ".csv": "#8B5CF6", ".zip": "#64748B",
        ".txt": "#94A3B8", ".html": "#06B6D4",
    }
    if ext.lower() in preset:
        return preset[ext.lower()]
    # 해시 기반 동적 색상
    h = int(hashlib.md5(ext.encode()).hexdigest()[:6], 16)
    hue = h % 360
    return f"hsl({hue}, 60%, 50%)"


# 확장자 아이콘
def _ext_icon(ext: str) -> str:
    icons = {
        ".xlsx": "📊", ".xls": "📊", ".pdf": "📕", ".docx": "📘", ".doc": "📘",
        ".pptx": "📙", ".ppt": "📙", ".jpg": "🖼", ".png": "🖼",
        ".csv": "📋", ".zip": "📦", ".txt": "📄",
    }
    return icons.get(ext.lower(), "📎")


class FilterChip(QPushButton):
    toggled_state = pyqtSignal(str, bool)

    def __init__(self, text, key="", parent=None):
        super().__init__(text, parent)
        self.key = key or text
        self._active = False
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(28)
        self.setFont(QFont("Segoe UI", Fonts.SIZE_SM))
        self._apply()
        self.clicked.connect(self._toggle)

    def _toggle(self):
        self._active = not self._active
        self._apply()
        self.toggled_state.emit(self.key, self._active)

    def set_active(self, active):
        self._active = active
        self._apply()

    @property
    def is_active(self):
        return self._active

    def _apply(self):
        if self._active:
            self.setStyleSheet(f"QPushButton{{background:{Colors.PRIMARY};color:#FFF;border:none;border-radius:6px;padding:4px 12px;font-weight:bold;}}")
        else:
            self.setStyleSheet(f"QPushButton{{background:{Colors.BG_CARD};color:{Colors.TEXT_SECONDARY};border:1px solid {Colors.BORDER};border-radius:6px;padding:4px 12px;}}QPushButton:hover{{background:{Colors.BG_CARD_HOVER};color:{Colors.TEXT_PRIMARY};}}")


class DynamicAttachmentFilter(QPushButton):
    """동적 첨부파일 필터 — DB에서 확장자 목록 자동 생성"""
    filter_changed = pyqtSignal(str)  # "" = 전체, ".xlsx" 등, "none" = 첨부없음

    def __init__(self, parent=None):
        super().__init__("📎 첨부 필터 ▾", parent)
        self._current = ""
        self._extensions = []
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(28)
        self.setFont(QFont("Segoe UI", Fonts.SIZE_SM))
        self.setStyleSheet(self._style(False))
        self.clicked.connect(self._show_menu)

    def update_extensions(self, db_conn):
        """DB에서 인덱싱된 확장자 목록 동적 로드"""
        self._extensions = []
        try:
            rows = db_conn.execute(
                "SELECT DISTINCT attachment_types FROM emails WHERE attachment_types != ''"
            ).fetchall()
            ext_set = set()
            for r in rows:
                for t in r["attachment_types"].split(", "):
                    t = t.strip()
                    if t:
                        ext_set.add(t)
            self._extensions = sorted(ext_set)
        except Exception:
            pass

    def _show_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu{{background:{Colors.BG_ELEVATED};color:{Colors.TEXT_PRIMARY};border:1px solid {Colors.BORDER_LIGHT};border-radius:8px;padding:4px;}}
            QMenu::item{{padding:6px 16px;border-radius:4px;}}
            QMenu::item:selected{{background:{Colors.PRIMARY};color:#FFF;}}
        """)

        # 전체
        a_all = QAction("전체 (필터 해제)", menu)
        a_all.setCheckable(True); a_all.setChecked(self._current == "")
        a_all.triggered.connect(lambda: self._select("", "전체"))
        menu.addAction(a_all)

        # ★ 첨부 있음
        a_has = QAction("📎 첨부 있음", menu)
        a_has.setCheckable(True); a_has.setChecked(self._current == "has")
        a_has.triggered.connect(lambda: self._select("has", "첨부 있음"))
        menu.addAction(a_has)

        # ★ 첨부 없음
        a_none = QAction("🚫 첨부 없음", menu)
        a_none.setCheckable(True); a_none.setChecked(self._current == "none")
        a_none.triggered.connect(lambda: self._select("none", "첨부 없음"))
        menu.addAction(a_none)

        menu.addSeparator()

        # ★ 동적 확장자 목록 (DB에서 자동 생성)
        for ext in self._extensions:
            icon = _ext_icon(ext)
            color = _ext_color(ext)
            label = f"{icon} {ext.upper().replace('.', '')} ({ext})"
            a = QAction(label, menu)
            a.setCheckable(True)
            a.setChecked(ext == self._current)
            a.triggered.connect(lambda checked, e=ext, l=label: self._select(e, l))
            menu.addAction(a)

        menu.exec(self.mapToGlobal(self.rect().bottomLeft()))

    def _select(self, value, label):
        self._current = value
        if value and value not in ("has", "none"):
            icon = _ext_icon(value)
            self.setText(f"{icon} {value.upper().replace('.', '')}")
            self.setStyleSheet(self._style(True))
        elif value == "has":
            self.setText("📎 첨부 있음")
            self.setStyleSheet(self._style(True))
        elif value == "none":
            self.setText("🚫 첨부 없음")
            self.setStyleSheet(self._style(True))
        else:
            self.setText("📎 첨부 필터 ▾")
            self.setStyleSheet(self._style(False))
        self.filter_changed.emit(value)

    def get_current(self) -> str:
        return self._current

    def reset(self):
        self._current = ""
        self.setText("📎 첨부 필터 ▾")
        self.setStyleSheet(self._style(False))

    def _style(self, active):
        if active:
            return f"QPushButton{{background:{Colors.PRIMARY}30;color:{Colors.PRIMARY_HOVER};border:1px solid {Colors.PRIMARY}60;border-radius:6px;padding:4px 10px;font-weight:bold;}}"
        return f"QPushButton{{background:{Colors.BG_CARD};color:{Colors.TEXT_SECONDARY};border:1px solid {Colors.BORDER};border-radius:6px;padding:4px 10px;}}QPushButton:hover{{background:{Colors.BG_CARD_HOVER};}}"


class FilterBar(QWidget):
    filter_changed = pyqtSignal()
    sort_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        row1 = QHBoxLayout()
        row1.setSpacing(5)

        self.chips = {}
        for key, label in [("all", "전체"), ("inbox", "받은편지함"), ("sent", "보낸편지함"), ("unread", "읽지 않음")]:
            chip = FilterChip(label, key)
            chip.toggled_state.connect(self._on_chip)
            self.chips[key] = chip
            row1.addWidget(chip)
        self.chips["all"].set_active(True)

        row1.addSpacing(4)

        # ★ 동적 첨부 필터
        self.att_filter = DynamicAttachmentFilter()
        self.att_filter.filter_changed.connect(lambda _: self.filter_changed.emit())
        row1.addWidget(self.att_filter)

        row1.addSpacing(4)

        # 날짜
        self.date_combo = QComboBox()
        self.date_combo.addItems(["전체 기간", "오늘", "최근 7일", "최근 30일", "최근 3개월", "최근 6개월", "최근 1년"])
        self.date_combo.setFixedHeight(28); self.date_combo.setFixedWidth(110)
        self.date_combo.setStyleSheet(self._combo())
        self.date_combo.currentTextChanged.connect(lambda: self.filter_changed.emit())
        row1.addWidget(self.date_combo)

        # 정렬
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["최신순", "관련도순", "오래된순"])
        self.sort_combo.setFixedHeight(28); self.sort_combo.setFixedWidth(95)
        self.sort_combo.setStyleSheet(self._combo())
        self.sort_combo.currentTextChanged.connect(self._on_sort)
        row1.addWidget(self.sort_combo)

        row1.addSpacing(4)

        self.reset_btn = QPushButton("↻ 초기화")
        self.reset_btn.setFixedHeight(28)
        self.reset_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.reset_btn.setStyleSheet(f"QPushButton{{background:transparent;color:{Colors.TEXT_DIM};border:1px solid {Colors.BORDER};border-radius:6px;padding:4px 8px;font-size:{Fonts.SIZE_XS}px;}}QPushButton:hover{{color:{Colors.ACCENT};border-color:{Colors.ACCENT}40;}}")
        self.reset_btn.clicked.connect(self.reset_all)
        self.reset_btn.hide()
        row1.addWidget(self.reset_btn)

        row1.addStretch()

        self.result_count = QLabel("")
        self.result_count.setFont(QFont("Segoe UI", Fonts.SIZE_XS))
        self.result_count.setStyleSheet(f"color:{Colors.TEXT_DIM};background:transparent;")
        row1.addWidget(self.result_count)

        w1 = QWidget(); w1.setLayout(row1); w1.setStyleSheet("background:transparent;")
        layout.addWidget(w1)

        # 활성 필터 태그
        self.tags_widget = QWidget()
        self.tags_widget.setStyleSheet("background:transparent;")
        self.tags_layout = QHBoxLayout(self.tags_widget)
        self.tags_layout.setContentsMargins(0, 0, 0, 0); self.tags_layout.setSpacing(4)
        tl = QLabel("활성 필터:")
        tl.setFont(QFont("Segoe UI", Fonts.SIZE_XS))
        tl.setStyleSheet(f"color:{Colors.TEXT_MUTED};background:transparent;")
        self.tags_layout.addWidget(tl)
        self.tags_layout.addStretch()
        self.tags_widget.hide()
        layout.addWidget(self.tags_widget)

    def set_result_count(self, total_db, result_count, elapsed_ms, mode="FTS5"):
        self.result_count.setText(f"{total_db:,}건 중 {result_count:,}건 · {elapsed_ms:.0f}ms · {mode}")

    def load_extensions_from_db(self, db_conn):
        """DB에서 동적 확장자 목록 로드"""
        self.att_filter.update_extensions(db_conn)

    def get_active_filters(self):
        return {k: c.is_active for k, c in self.chips.items()}

    def get_sort_mode(self):
        m = {"관련도순": "rank", "최신순": "received_at_desc", "오래된순": "received_at_asc"}
        return m.get(self.sort_combo.currentText(), "received_at_desc")

    def get_date_filter(self):
        return self.date_combo.currentText()

    def get_attachment_filter(self) -> str:
        """'', 'has', 'none', '.xlsx' 등"""
        return self.att_filter.get_current()

    def get_filter_state(self):
        return {
            "chips": {k: c.is_active for k, c in self.chips.items()},
            "date": self.date_combo.currentText(),
            "sort": self.sort_combo.currentText(),
            "att": self.att_filter.get_current(),
        }

    def restore_filter_state(self, state):
        if not state: return
        for k, v in state.get("chips", {}).items():
            if k in self.chips: self.chips[k].set_active(v)
        idx = self.date_combo.findText(state.get("date", "전체 기간"))
        if idx >= 0: self.date_combo.setCurrentIndex(idx)
        idx = self.sort_combo.findText(state.get("sort", "최신순"))
        if idx >= 0: self.sort_combo.setCurrentIndex(idx)

    def reset_all(self):
        for k, c in self.chips.items(): c.set_active(k == "all")
        self.date_combo.setCurrentIndex(0)
        self.sort_combo.setCurrentIndex(0)
        self.att_filter.reset()
        self.reset_btn.hide()
        self._update_tags()
        self.filter_changed.emit()

    def _on_chip(self, key, active):
        if key == "all" and active:
            for k, c in self.chips.items():
                if k != "all": c.set_active(False)
        elif key != "all" and active:
            self.chips["all"].set_active(False)
        self._update_tags()
        self.filter_changed.emit()

    def _on_sort(self, text):
        m = {"관련도순": "rank", "최신순": "received_at_desc", "오래된순": "received_at_asc"}
        self.sort_changed.emit(m.get(text, "received_at_desc"))

    def _update_tags(self):
        while self.tags_layout.count() > 2:
            item = self.tags_layout.takeAt(1)
            if item.widget(): item.widget().deleteLater()
        tags = []
        for k, c in self.chips.items():
            if k != "all" and c.is_active: tags.append(c.text())
        if self.date_combo.currentText() != "전체 기간": tags.append(self.date_combo.currentText())
        att = self.att_filter.get_current()
        if att: tags.append(f"첨부:{att}")
        if tags:
            self.tags_widget.show(); self.reset_btn.show()
            for t in tags:
                l = QLabel(f"  {t}  "); l.setFont(QFont("Segoe UI", Fonts.SIZE_XS))
                l.setStyleSheet(f"background:{Colors.PRIMARY}20;color:{Colors.PRIMARY_HOVER};border:1px solid {Colors.PRIMARY}40;border-radius:4px;padding:1px 6px;")
                self.tags_layout.insertWidget(self.tags_layout.count()-1, l)
        else:
            self.tags_widget.hide(); self.reset_btn.hide()

    def _combo(self):
        return f"QComboBox{{background:{Colors.BG_CARD};color:{Colors.TEXT_SECONDARY};border:1px solid {Colors.BORDER};border-radius:6px;padding:4px 8px;font-size:{Fonts.SIZE_SM}px;}}QComboBox:hover{{border-color:{Colors.BORDER_LIGHT};}}QComboBox::drop-down{{border:none;width:18px;}}QComboBox QAbstractItemView{{background:{Colors.BG_ELEVATED};color:{Colors.TEXT_PRIMARY};selection-background-color:{Colors.PRIMARY};border:1px solid {Colors.BORDER_LIGHT};border-radius:6px;padding:4px;}}"
