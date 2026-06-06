"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[U09] 인덱싱 진행률 다이얼로그 (v2 — 스마트 동기화 지원)

개선: plan_ready 시그널로 "변경 없음" 상태를 사용자에게 안내
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QCursor

from ui.theme import Colors, Fonts, Radius, APP_FULL_NAME


class IndexingDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_FULL_NAME} — 인덱싱")
        self.setFixedSize(540, 500)
        self.setStyleSheet(f"background-color: {Colors.BG_MAIN};")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)

        self._is_paused = False
        self._is_finished = False

        self.on_pause_clicked = None
        self.on_resume_clicked = None
        self.on_stop_clicked = None
        self.on_background_clicked = None

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 22, 30, 18)
        layout.setSpacing(12)

        # 헤더
        self.title_label = QLabel("📧 메일 인덱싱 진행 중...")
        self.title_label.setFont(QFont("Segoe UI", Fonts.SIZE_XL, QFont.Weight.Bold))
        self.title_label.setStyleSheet(f"color:{Colors.TEXT_PRIMARY}; background:transparent;")
        layout.addWidget(self.title_label)

        # 프로그레스 바
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{ background-color:{Colors.BG_CARD}; border:none; border-radius:4px; }}
            QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {Colors.PRIMARY},stop:1 {Colors.ACCENT}); border-radius:4px; }}
        """)
        layout.addWidget(self.progress_bar)

        # 퍼센트
        self.pct_label = QLabel("0%")
        self.pct_label.setFont(QFont("Segoe UI", Fonts.SIZE_3XL, QFont.Weight.Bold))
        self.pct_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pct_label.setStyleSheet(f"color:{Colors.ACCENT}; background:transparent;")
        layout.addWidget(self.pct_label)

        # ── 변경 사항 요약 (스마트 동기화용) ──
        self.plan_widget = QWidget()
        self.plan_widget.setStyleSheet(f"background:{Colors.BG_CARD};border:1px solid {Colors.BORDER};border-radius:{Radius.MD}px;")
        self.plan_widget.hide()
        pw = QVBoxLayout(self.plan_widget)
        pw.setContentsMargins(16, 10, 16, 10)
        pw.setSpacing(4)

        self.plan_title = QLabel("📋 동기화 계획")
        self.plan_title.setFont(QFont("Segoe UI", Fonts.SIZE_SM, QFont.Weight.Bold))
        self.plan_title.setStyleSheet(f"color:{Colors.TEXT_SECONDARY};background:transparent;border:none;")
        pw.addWidget(self.plan_title)

        self.plan_detail = QLabel("")
        self.plan_detail.setFont(QFont("Segoe UI", Fonts.SIZE_SM))
        self.plan_detail.setStyleSheet(f"color:{Colors.TEXT_DIM};background:transparent;border:none;")
        self.plan_detail.setWordWrap(True)
        pw.addWidget(self.plan_detail)
        layout.addWidget(self.plan_widget)

        # 통계 카드
        stats_card = QWidget()
        stats_card.setStyleSheet(f"background:{Colors.BG_CARD};border:1px solid {Colors.BORDER};border-radius:{Radius.LG}px;")
        s_layout = QVBoxLayout(stats_card)
        s_layout.setContentsMargins(18, 12, 18, 12)
        s_layout.setSpacing(6)

        self.stat_labels = {}
        stats = [
            ("total",     "📊 전체",     "계산 중..."),
            ("done",      "✅ 완료",     "0건"),
            ("remaining", "⏱ 남은 시간",  "계산 중..."),
            ("speed",     "⚡ 처리 속도", "—"),
            ("detail",    "📋 상세",     "—"),
        ]
        for key, label, value in stats:
            row = QHBoxLayout()
            l = QLabel(label)
            l.setFont(QFont("Segoe UI", Fonts.SIZE_SM))
            l.setStyleSheet(f"color:{Colors.TEXT_DIM};background:transparent;border:none;")
            row.addWidget(l)
            row.addStretch()
            v = QLabel(value)
            v.setFont(QFont("Segoe UI", Fonts.SIZE_SM, QFont.Weight.Bold))
            v.setStyleSheet(f"color:{Colors.TEXT_SECONDARY};background:transparent;border:none;")
            v.setWordWrap(True)
            self.stat_labels[key] = v
            row.addWidget(v)
            s_layout.addLayout(row)

        layout.addWidget(stats_card)

        # 최근 메일
        self.recent_label = QLabel("📝 준비 중...")
        self.recent_label.setFont(QFont("Segoe UI", Fonts.SIZE_XS))
        self.recent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.recent_label.setStyleSheet(f"color:{Colors.TEXT_MUTED};background:transparent;")
        layout.addWidget(self.recent_label)

        layout.addStretch()

        # 버튼 행
        self.btn_row = QHBoxLayout()
        self.btn_row.setSpacing(8)

        self.pause_btn = self._make_btn("⏸ 일시정지", Colors.WARNING)
        self.pause_btn.clicked.connect(self._on_pause)
        self.btn_row.addWidget(self.pause_btn)

        self.stop_btn = self._make_btn("⏹ 중단", Colors.DANGER)
        self.stop_btn.clicked.connect(self._on_stop)
        self.btn_row.addWidget(self.stop_btn)

        self.bg_btn = QPushButton("🔽 백그라운드")
        self.bg_btn.setFixedHeight(36)
        self.bg_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.bg_btn.setStyleSheet(f"QPushButton{{background:{Colors.BG_CARD};color:{Colors.TEXT_SECONDARY};border:1px solid {Colors.BORDER};border-radius:8px;padding:6px 14px;font-size:{Fonts.SIZE_SM}px;}}QPushButton:hover{{background:{Colors.BG_CARD_HOVER};}}")
        self.bg_btn.clicked.connect(self._on_background)
        self.btn_row.addWidget(self.bg_btn)

        layout.addLayout(self.btn_row)

        note = QLabel("⚠ 인덱싱 중에도 이미 처리된 메일은 검색 가능합니다")
        note.setFont(QFont("Segoe UI", Fonts.SIZE_XS))
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setStyleSheet(f"color:{Colors.TEXT_MUTED};background:transparent;")
        layout.addWidget(note)

    # ── 업데이트 메서드 ──

    def update_progress(self, done: int, total: int, message: str, folder: str = ""):
        if total > 0:
            pct = min(int(done / total * 100), 100)
        else:
            pct = 0
        self.progress_bar.setValue(pct)
        self.pct_label.setText(f"{pct}%")
        self.stat_labels["total"].setText(f"{total:,}건")
        self.stat_labels["done"].setText(f"{done:,}건")
        if message:
            display = message[:50] + "..." if len(message) > 50 else message
            self.recent_label.setText(f"📝 {display}")

    def update_speed(self, mails_per_sec: float):
        self.stat_labels["speed"].setText(f"약 {mails_per_sec:.1f}건/초")
        try:
            done_text = self.stat_labels["done"].text().replace(",", "").replace("건", "")
            total_text = self.stat_labels["total"].text().replace(",", "").replace("건", "")
            done = int(done_text) if done_text.isdigit() else 0
            total = int(total_text) if total_text.isdigit() else 0
            remaining = total - done
            if mails_per_sec > 0 and remaining > 0:
                secs = remaining / mails_per_sec
                if secs < 60:
                    self.stat_labels["remaining"].setText(f"약 {int(secs)}초")
                else:
                    self.stat_labels["remaining"].setText(f"약 {int(secs//60)}분 {int(secs%60)}초")
        except Exception:
            pass

    def on_plan_ready(self, summary: str, has_changes: bool):
        """스마트 동기화 계획 수립 완료 시"""
        self.plan_widget.show()
        if has_changes:
            self.plan_title.setText("📋 동기화 계획")
            self.plan_detail.setText(summary)
        else:
            self.plan_title.setText("✅ 이미 최신 상태")
            self.plan_detail.setText(summary)
            self.plan_detail.setStyleSheet(f"color:{Colors.SUCCESS};background:transparent;border:none;")

    def on_indexing_finished(self, stats: dict):
        self._is_finished = True
        self.progress_bar.setValue(100)

        message = stats.get("message", "")
        added = stats.get("added", stats.get("indexed", 0))
        updated = stats.get("updated", 0)
        deleted = stats.get("deleted", 0)
        skipped = stats.get("skipped", 0)
        errors = stats.get("errors", 0)
        elapsed = stats.get("elapsed_sec", 0)

        # 변경 없었으면 특별 UI
        if added == 0 and updated == 0 and deleted == 0 and skipped > 0:
            self.pct_label.setText("✅")
            self.pct_label.setStyleSheet(f"color:{Colors.SUCCESS};background:transparent;font-size:48px;")
            self.title_label.setText("✅ 모든 메일이 최신 상태입니다")
            self.stat_labels["remaining"].setText("동기화 불필요")
            self.stat_labels["remaining"].setStyleSheet(f"color:{Colors.SUCCESS};background:transparent;border:none;")
        else:
            self.pct_label.setText("100%")
            self.pct_label.setStyleSheet(f"color:{Colors.SUCCESS};background:transparent;")
            self.title_label.setText("✅ 인덱싱 완료!")
            self.stat_labels["remaining"].setText("완료!")
            self.stat_labels["remaining"].setStyleSheet(f"color:{Colors.SUCCESS};background:transparent;border:none;")

        # 상세 통계
        detail_parts = []
        if added:
            detail_parts.append(f"추가 {added}건")
        if updated:
            detail_parts.append(f"업데이트 {updated}건")
        if deleted:
            detail_parts.append(f"삭제 {deleted}건")
        if skipped:
            detail_parts.append(f"스킵 {skipped:,}건")
        if errors:
            detail_parts.append(f"오류 {errors}건")
        self.stat_labels["detail"].setText(" · ".join(detail_parts) if detail_parts else "—")

        self.stat_labels["done"].setText(f"{added + updated}건 처리")
        self.recent_label.setText(f"⏱ {elapsed}초 소요 · {message}" if message else f"⏱ {elapsed}초 소요")

        # 버튼 변경
        self.pause_btn.hide()
        self.stop_btn.hide()
        self.bg_btn.hide()

        close_btn = QPushButton("✅ 닫기")
        close_btn.setFixedHeight(42)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.setStyleSheet(f"QPushButton{{background:{Colors.SUCCESS};color:#FFF;border:none;border-radius:8px;padding:8px 24px;font-size:{Fonts.SIZE_BASE}px;font-weight:bold;}}QPushButton:hover{{background:#34D399;}}")
        close_btn.clicked.connect(self.accept)
        self.btn_row.addWidget(close_btn)

    def on_indexing_error(self, error_msg: str):
        self.title_label.setText("❌ 인덱싱 오류 발생")
        self.recent_label.setText(f"⚠ {error_msg}")
        self.recent_label.setStyleSheet(f"color:{Colors.DANGER};background:transparent;")

    # ── 내부 ──

    def _on_pause(self):
        self._is_paused = not self._is_paused
        if self._is_paused:
            self.pause_btn.setText("▶ 재개")
            self.pause_btn.setStyleSheet(self._btn_style(Colors.SUCCESS))
            self.title_label.setText("⏸ 인덱싱 일시정지")
            if self.on_pause_clicked:
                self.on_pause_clicked()
        else:
            self.pause_btn.setText("⏸ 일시정지")
            self.pause_btn.setStyleSheet(self._btn_style(Colors.WARNING))
            self.title_label.setText("📧 메일 인덱싱 진행 중...")
            if self.on_resume_clicked:
                self.on_resume_clicked()

    def _on_stop(self):
        if self.on_stop_clicked:
            self.on_stop_clicked()
        self.reject()

    def _on_background(self):
        if self.on_background_clicked:
            self.on_background_clicked()
        self.hide()

    def _make_btn(self, text, color):
        btn = QPushButton(text)
        btn.setFixedHeight(36)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setStyleSheet(self._btn_style(color))
        return btn

    def _btn_style(self, color):
        return f"QPushButton{{background:{color}20;color:{color};border:1px solid {color}40;border-radius:8px;padding:6px 14px;font-size:{Fonts.SIZE_SM}px;font-weight:bold;}}QPushButton:hover{{background:{color}35;}}"
