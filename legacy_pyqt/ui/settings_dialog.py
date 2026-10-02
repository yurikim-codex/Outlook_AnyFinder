"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[U11] 설정 화면

인덱싱 범위, 동기화 주기, 자동완성 설정, DB 관리 등
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QComboBox, QSpinBox, QWidget, QFrame, QMessageBox,
    QTabWidget, QGroupBox, QRadioButton, QButtonGroup, QProgressDialog,
    QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QCursor

from ui.theme import Colors, Fonts, Radius, APP_FULL_NAME
from utils.config import load_config, save_config


class SettingsDialog(QDialog):
    """설정 다이얼로그"""

    settings_saved = pyqtSignal(dict)  # 저장 시 변경된 설정 emit
    data_reset = pyqtSignal()          # 데이터 초기화 완료 시 emit

    def __init__(self, db_conn=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_FULL_NAME} — 설정")
        # 탭이 늘어나도 메뉴가 잘리지 않도록 고정 크기 대신 가변 크기 사용
        self.setMinimumSize(680, 640)
        self.resize(760, 700)
        self.setStyleSheet(f"background-color:{Colors.BG_MAIN};")

        self.conn = db_conn
        self.config = load_config()
        self._build()
        self._load_values()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 18)
        layout.setSpacing(14)

        # 타이틀
        title = QLabel("⚙ 설정")
        title.setFont(QFont("Segoe UI", Fonts.SIZE_2XL, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{Colors.TEXT_PRIMARY};background:transparent;")
        layout.addWidget(title)

        # 탭 위젯
        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane{{border:1px solid {Colors.BORDER};border-radius:{Radius.MD}px;background:{Colors.BG_CARD};}}
            QTabBar::tab{{background:{Colors.BG_CARD};color:{Colors.TEXT_DIM};border:1px solid {Colors.BORDER};padding:8px 18px;margin-right:2px;border-top-left-radius:8px;border-top-right-radius:8px;}}
            QTabBar::tab:selected{{background:{Colors.PRIMARY_BG};color:{Colors.PRIMARY_HOVER};font-weight:bold;border-bottom-color:{Colors.BG_CARD};}}
            QTabBar::tab:hover{{color:{Colors.TEXT_PRIMARY};}}
        """)

        tabs.addTab(self._tab_indexing(), "📧 인덱싱")
        tabs.addTab(self._tab_sync(), "🔄 동기화")
        tabs.addTab(self._tab_search(), "🔍 검색")
        tabs.addTab(self._tab_theme(), "🎨 UI 테마")
        tabs.addTab(self._tab_data(), "💾 데이터")

        layout.addWidget(tabs, 1)

        # 하단 버튼
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        cancel_btn = QPushButton("취소")
        cancel_btn.setFixedHeight(38)
        cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_btn.setStyleSheet(f"QPushButton{{background:transparent;color:{Colors.TEXT_DIM};border:1px solid {Colors.BORDER};border-radius:8px;padding:6px 24px;}}QPushButton:hover{{background:{Colors.BG_CARD_HOVER};}}")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        btn_row.addStretch()

        save_btn = QPushButton("✅ 저장")
        save_btn.setFixedHeight(38)
        save_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        save_btn.setStyleSheet(f"QPushButton{{background:{Colors.PRIMARY};color:#FFF;border:none;border-radius:8px;padding:6px 28px;font-weight:bold;}}QPushButton:hover{{background:{Colors.PRIMARY_HOVER};}}")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    # ── 탭 구성 ──

    def _tab_indexing(self):
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(self._section_label("인덱싱 대상 폴더"))

        self.folder_checks = {}
        for fid, text, default in [(6, "📥 받은편지함", True), (5, "📤 보낸편지함", True),
                                     (16, "📝 임시보관함", False), (3, "🗑 지운편지함", False)]:
            cb = self._make_check(text, default)
            self.folder_checks[fid] = cb
            layout.addWidget(cb)

        self.subfolder_check = self._make_check("📂 하위 폴더 포함", True)
        layout.addWidget(self.subfolder_check)

        layout.addSpacing(8)
        layout.addWidget(self._section_label("인덱싱 범위"))

        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("최대 범위:"))
        self.range_combo = QComboBox()
        self.range_combo.addItems(["3개월", "6개월", "1년", "전체"])
        self.range_combo.setFixedWidth(120)
        self.range_combo.setStyleSheet(self._combo_style())
        range_row.addWidget(self.range_combo)
        range_row.addStretch()
        layout.addLayout(range_row)

        layout.addStretch()
        return w

    def _tab_sync(self):
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(self._section_label("자동 동기화"))

        self.auto_sync_check = self._make_check("자동 동기화 활성화", True)
        layout.addWidget(self.auto_sync_check)

        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel("동기화 주기:"))
        self.interval_combo = QComboBox()
        self.interval_combo.addItems(["5분", "10분", "30분", "1시간", "수동만"])
        self.interval_combo.setFixedWidth(120)
        self.interval_combo.setStyleSheet(self._combo_style())
        interval_row.addWidget(self.interval_combo)
        interval_row.addStretch()
        layout.addLayout(interval_row)

        layout.addSpacing(8)

        info = QLabel(
            "💡 동기화는 스마트 증분 방식으로 동작합니다.\n"
            "   변경된 메일만 감지하여 처리하므로 빠릅니다.\n"
            "   동일한 메일은 자동으로 스킵됩니다."
        )
        info.setFont(QFont("Segoe UI", Fonts.SIZE_XS))
        info.setStyleSheet(f"color:{Colors.TEXT_DIM};background:{Colors.BG_CARD};border:1px solid {Colors.BORDER};border-radius:8px;padding:10px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addStretch()
        return w

    def _tab_search(self):
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(self._section_label("자동완성"))

        ac_row = QHBoxLayout()
        ac_row.addWidget(QLabel("최대 표시 수:"))
        self.ac_max_spin = QSpinBox()
        self.ac_max_spin.setRange(3, 15)
        self.ac_max_spin.setValue(8)
        self.ac_max_spin.setFixedWidth(80)
        self.ac_max_spin.setStyleSheet(f"QSpinBox{{background:{Colors.BG_INPUT};color:{Colors.TEXT_PRIMARY};border:1px solid {Colors.BORDER};border-radius:6px;padding:4px 8px;}}")
        ac_row.addWidget(self.ac_max_spin)
        ac_row.addStretch()
        layout.addLayout(ac_row)

        layout.addWidget(self._section_label("검색 결과"))

        pp_row = QHBoxLayout()
        pp_row.addWidget(QLabel("페이지당 결과 수:"))
        self.per_page_combo = QComboBox()
        self.per_page_combo.addItems(["10", "20", "30", "50"])
        self.per_page_combo.setCurrentText("20")
        self.per_page_combo.setFixedWidth(80)
        self.per_page_combo.setStyleSheet(self._combo_style())
        pp_row.addWidget(self.per_page_combo)
        pp_row.addStretch()
        layout.addLayout(pp_row)

        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel("기본 정렬:"))
        self.default_sort_combo = QComboBox()
        self.default_sort_combo.addItems(["관련도순", "최신순", "오래된순"])
        self.default_sort_combo.setFixedWidth(120)
        self.default_sort_combo.setStyleSheet(self._combo_style())
        sort_row.addWidget(self.default_sort_combo)
        sort_row.addStretch()
        layout.addLayout(sort_row)

        layout.addStretch()
        return w

    def _tab_theme(self):
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        layout.addWidget(self._section_label("UI 테마"))

        self.theme_group = QButtonGroup(self)
        self.theme_radios = {}

        for key, title, desc in [
            ("dark", "🌙 모던 다크 테마", "Slack 스타일의 심플한 사이드바와 Outlook 스타일 카드형 검색 리스트"),
            ("light", "☀ 화이트 테마", "밝은 배경, 부드러운 색상 계층, 명확한 선택 상태"),
        ]:
            card = QWidget()
            card.setStyleSheet(f"background:{Colors.BG_CARD};border:1px solid {Colors.BORDER};border-radius:{Radius.MD}px;")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 12, 14, 12)
            cl.setSpacing(4)

            rb = QRadioButton(title)
            rb.setFont(QFont("Segoe UI", Fonts.SIZE_BASE, QFont.Weight.Bold))
            rb.setStyleSheet(f"""
                QRadioButton {{ color:{Colors.TEXT_PRIMARY}; spacing:8px; background:transparent; border:none; }}
                QRadioButton::indicator {{ width:16px; height:16px; border:2px solid {Colors.TEXT_DIM}; border-radius:8px; background:transparent; }}
                QRadioButton::indicator:checked {{ background-color:{Colors.PRIMARY}; border-color:{Colors.PRIMARY}; }}
            """)
            self.theme_group.addButton(rb)
            self.theme_radios[key] = rb
            cl.addWidget(rb)

            info = QLabel(desc)
            info.setWordWrap(True)
            info.setFont(QFont("Segoe UI", Fonts.SIZE_SM))
            info.setStyleSheet(f"color:{Colors.TEXT_DIM};background:transparent;border:none;padding-left:24px;")
            cl.addWidget(info)
            layout.addWidget(card)

        note = QLabel("저장하면 선택한 테마가 즉시 적용됩니다. 일부 열린 설정창 스타일은 다음에 열 때 완전히 반영됩니다.")
        note.setWordWrap(True)
        note.setFont(QFont("Segoe UI", Fonts.SIZE_XS))
        note.setStyleSheet(f"color:{Colors.TEXT_DIM};background:{Colors.ACCENT_BG};border:1px solid {Colors.ACCENT}30;border-radius:8px;padding:10px;")
        layout.addWidget(note)

        layout.addStretch()
        return w

    def _tab_data(self):
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(self._section_label("데이터 관리"))

        # DB 정보
        self.db_info = QLabel("DB 정보 로딩 중...")
        self.db_info.setFont(QFont("Segoe UI", Fonts.SIZE_SM))
        self.db_info.setStyleSheet(f"color:{Colors.TEXT_SECONDARY};background:{Colors.BG_CARD};border:1px solid {Colors.BORDER};border-radius:8px;padding:10px;")
        self.db_info.setWordWrap(True)
        layout.addWidget(self.db_info)
        self._update_db_info()

        # 버튼들
        btn_style = f"QPushButton{{background:{Colors.BG_CARD};color:{Colors.TEXT_SECONDARY};border:1px solid {Colors.BORDER};border-radius:8px;padding:8px 16px;}}QPushButton:hover{{background:{Colors.BG_CARD_HOVER};color:{Colors.TEXT_PRIMARY};}}"

        clear_hist_btn = QPushButton("🗑 검색 히스토리 초기화")
        clear_hist_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        clear_hist_btn.setStyleSheet(btn_style)
        clear_hist_btn.clicked.connect(self._clear_history)
        layout.addWidget(clear_hist_btn)

        rebuild_btn = QPushButton("🔄 검색 인덱스 재구축 (FTS5)")
        rebuild_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        rebuild_btn.setStyleSheet(btn_style)
        rebuild_btn.clicked.connect(self._rebuild_fts)
        layout.addWidget(rebuild_btn)

        danger_btn = QPushButton("⚠ 전체 데이터 삭제 및 초기화")
        danger_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        danger_btn.setStyleSheet(f"QPushButton{{background:{Colors.DANGER}15;color:{Colors.DANGER};border:1px solid {Colors.DANGER}40;border-radius:8px;padding:8px 16px;}}QPushButton:hover{{background:{Colors.DANGER}30;}}")
        danger_btn.clicked.connect(self._reset_all_data)
        layout.addWidget(danger_btn)

        layout.addStretch()
        return w

    # ── 값 로드/저장 ──

    def _load_values(self):
        idx = self.config.get("indexing", {})
        folder_ids = idx.get("folder_ids", [6, 5])
        for fid, cb in self.folder_checks.items():
            cb.setChecked(fid in folder_ids)
        self.subfolder_check.setChecked(idx.get("include_subfolders", True))

        range_months = idx.get("range_months", 6)
        range_map = {3: "3개월", 6: "6개월", 12: "1년", 0: "전체"}
        self.range_combo.setCurrentText(range_map.get(range_months, "6개월"))

        sync = self.config.get("sync", {})
        self.auto_sync_check.setChecked(sync.get("auto_sync", True))
        interval = sync.get("interval_minutes", 10)
        interval_map = {5: "5분", 10: "10분", 30: "30분", 60: "1시간"}
        self.interval_combo.setCurrentText(interval_map.get(interval, "10분"))

        search = self.config.get("search", {})
        self.ac_max_spin.setValue(search.get("max_autocomplete_items", 8))
        self.per_page_combo.setCurrentText(str(search.get("results_per_page", 20)))

        sort_map = {"relevance": "관련도순", "newest": "최신순", "oldest": "오래된순"}
        self.default_sort_combo.setCurrentText(sort_map.get(search.get("default_sort", "relevance"), "관련도순"))

        theme = self.config.get("ui", {}).get("theme", "dark")
        self.theme_radios.get(theme, self.theme_radios["dark"]).setChecked(True)

    def _on_save(self):
        folder_ids = [fid for fid, cb in self.folder_checks.items() if cb.isChecked()]
        range_map = {"3개월": 3, "6개월": 6, "1년": 12, "전체": 0}
        interval_map = {"5분": 5, "10분": 10, "30분": 30, "1시간": 60, "수동만": 0}
        sort_map = {"관련도순": "relevance", "최신순": "newest", "오래된순": "oldest"}

        self.config["indexing"]["folder_ids"] = folder_ids
        self.config["indexing"]["include_subfolders"] = self.subfolder_check.isChecked()
        self.config["indexing"]["range_months"] = range_map.get(self.range_combo.currentText(), 6)

        self.config["sync"]["auto_sync"] = self.auto_sync_check.isChecked() and self.interval_combo.currentText() != "수동만"
        self.config["sync"]["interval_minutes"] = interval_map.get(self.interval_combo.currentText(), 10)

        self.config["search"]["max_autocomplete_items"] = self.ac_max_spin.value()
        self.config["search"]["results_per_page"] = int(self.per_page_combo.currentText())
        self.config["search"]["default_sort"] = sort_map.get(self.default_sort_combo.currentText(), "relevance")

        self.config.setdefault("ui", {})["theme"] = "light" if self.theme_radios["light"].isChecked() else "dark"

        save_config(self.config)
        self.settings_saved.emit(self.config)
        self.accept()

    # ── 데이터 관리 ──

    def _update_db_info(self):
        if not self.conn:
            self.db_info.setText("DB 연결 없음")
            return
        try:
            email_cnt = self.conn.execute("SELECT COUNT(*) as n FROM emails").fetchone()["n"]
            hist_cnt = self.conn.execute("SELECT COUNT(*) as n FROM search_history").fetchone()["n"]
            bm_cnt = self.conn.execute("SELECT COUNT(*) as n FROM bookmarks").fetchone()["n"]

            from data.database import DB_PATH
            import os
            db_size = os.path.getsize(DB_PATH) / 1024 / 1024 if DB_PATH.exists() else 0

            self.db_info.setText(
                f"📊 인덱싱 메일: {email_cnt:,}건\n"
                f"🕐 검색 히스토리: {hist_cnt}건\n"
                f"⭐ 북마크: {bm_cnt}건\n"
                f"💾 DB 크기: {db_size:.1f}MB\n"
                f"📁 위치: {DB_PATH}"
            )
        except Exception as e:
            self.db_info.setText(f"정보 조회 실패: {e}")

    def _clear_history(self):
        reply = self._ask_yes_no(
            "검색 히스토리 초기화",
            "검색 히스토리를 모두 삭제하시겠습니까?",
            yes_text="Yes  삭제",
            no_text="No  취소",
            danger=False,
        )
        if reply == QMessageBox.StandardButton.Yes and self.conn:
            progress = self._make_progress("검색 히스토리 초기화", "검색 히스토리 삭제 중...", 3)
            try:
                progress.setValue(1); QApplication.processEvents()
                self.conn.execute("DELETE FROM search_history")
                progress.setLabelText("검색 세션 기록 삭제 중..."); progress.setValue(2); QApplication.processEvents()
                self.conn.execute("DELETE FROM search_sessions")
                self.conn.commit()
                progress.setValue(3); QApplication.processEvents()
                self._update_db_info()
                QMessageBox.information(self, "완료", "검색 히스토리가 초기화되었습니다.")
            finally:
                progress.close()

    def _rebuild_fts(self):
        reply = self._ask_yes_no(
            "검색 인덱스 재구축",
            "검색 인덱스를 재구축하시겠습니까?\n메일 수에 따라 시간이 걸릴 수 있습니다.",
            yes_text="Yes  재구축",
            no_text="No  취소",
            danger=False,
        )
        if reply == QMessageBox.StandardButton.Yes and self.conn:
            progress = self._make_progress("검색 인덱스 재구축", "FTS5 검색 인덱스 재구축 중...", 3)
            try:
                progress.setValue(1); QApplication.processEvents()
                self.conn.execute("INSERT INTO emails_fts(emails_fts) VALUES('rebuild')")
                progress.setLabelText("DB 변경사항 저장 중..."); progress.setValue(2); QApplication.processEvents()
                self.conn.commit()
                progress.setValue(3); QApplication.processEvents()
                QMessageBox.information(self, "완료", "검색 인덱스가 재구축되었습니다.")
            except Exception as e:
                QMessageBox.warning(self, "오류", f"재구축 실패: {e}")
            finally:
                progress.close()

    def _reset_all_data(self):
        reply = self._ask_yes_no(
            "⚠ 데이터 초기화",
            "모든 인덱싱 데이터, 검색 히스토리, 북마크가 삭제됩니다.\n\n정말로 초기화하시겠습니까?",
            yes_text="Yes  초기화",
            no_text="No  취소",
        )
        if reply == QMessageBox.StandardButton.Yes and self.conn:
            tables = ["emails", "email_hashes", "search_history", "bookmarks", "search_sessions", "related_keywords", "sync_meta"]
            progress = self._make_progress("데이터 초기화", "초기화 준비 중...", len(tables) + 4)
            try:
                step = 0
                for table in tables:
                    step += 1
                    progress.setLabelText(f"{table} 테이블 초기화 중...")
                    progress.setValue(step)
                    QApplication.processEvents()
                    self.conn.execute(f"DELETE FROM {table}")
                step += 1
                progress.setLabelText("검색 인덱스 재구축 중...")
                progress.setValue(step); QApplication.processEvents()
                self.conn.execute("INSERT INTO emails_fts(emails_fts) VALUES('rebuild')")
                step += 1
                progress.setLabelText("DB 변경사항 저장 중...")
                progress.setValue(step); QApplication.processEvents()
                self.conn.commit()
                step += 1
                progress.setLabelText("설정 초기화 중...")
                progress.setValue(step); QApplication.processEvents()
                self.config["first_run_completed"] = False
                save_config(self.config)
                step += 1
                progress.setLabelText("화면 갱신 중...")
                progress.setValue(step); QApplication.processEvents()
                self._update_db_info()
                self.data_reset.emit()
                QMessageBox.information(self, "완료", "데이터가 초기화되었습니다.\n폴더 카운트와 검색 목록도 초기화했습니다.")
            except Exception as e:
                QMessageBox.warning(self, "오류", f"초기화 실패: {e}")
            finally:
                progress.close()

    # ── 헬퍼 ──

    def _make_progress(self, title: str, label: str, maximum: int):
        progress = QProgressDialog(label, None, 0, maximum, self)
        progress.setWindowTitle(title)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setStyleSheet(f"""
            QProgressDialog {{ background:{Colors.BG_MAIN}; color:{Colors.TEXT_PRIMARY}; }}
            QProgressBar {{ background:{Colors.BG_INPUT}; border:none; border-radius:5px; height:10px; }}
            QProgressBar::chunk {{ background:{Colors.PRIMARY}; border-radius:5px; }}
            QLabel {{ color:{Colors.TEXT_PRIMARY}; background:transparent; }}
        """)
        progress.show()
        QApplication.processEvents()
        return progress

    def _ask_yes_no(self, title: str, text: str, yes_text="Yes", no_text="No", danger=True):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        yes_btn = box.button(QMessageBox.StandardButton.Yes)
        no_btn = box.button(QMessageBox.StandardButton.No)
        if yes_btn:
            yes_btn.setText(yes_text)
        if no_btn:
            no_btn.setText(no_text)
        accent = Colors.DANGER if danger else Colors.PRIMARY
        box.setStyleSheet(f"""
            QMessageBox {{ background-color:{Colors.BG_MAIN}; color:{Colors.TEXT_PRIMARY}; }}
            QMessageBox QLabel {{ color:{Colors.TEXT_PRIMARY}; background:transparent; font-size:{Fonts.SIZE_BASE}px; }}
            QMessageBox QPushButton {{
                min-width:122px; min-height:36px; padding:8px 20px;
                margin-left:8px; margin-right:8px;
                border-radius:14px; font-weight:700;
                border:1px solid {Colors.BORDER_LIGHT};
                background:{Colors.BG_CARD}; color:{Colors.TEXT_SECONDARY};
            }}
            QMessageBox QPushButton:hover {{
                border:2px solid {Colors.PRIMARY};
                background:{Colors.BG_CARD_HOVER}; color:{Colors.TEXT_PRIMARY};
            }}
            QMessageBox QPushButton:default {{
                background:{accent}; color:#FFFFFF; border:1px solid {accent};
            }}
            QMessageBox QPushButton:default:hover {{
                border:2px solid {accent};
            }}
        """)
        return box.exec()

    def _section_label(self, text):
        lbl = QLabel(text)
        lbl.setFont(QFont("Segoe UI", Fonts.SIZE_SM, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{Colors.TEXT_SECONDARY};background:transparent;")
        return lbl

    def _make_check(self, text, checked):
        cb = QCheckBox(text)
        cb.setChecked(checked)
        cb.setFont(QFont("Segoe UI", Fonts.SIZE_SM))
        cb.setStyleSheet(f"""
            QCheckBox{{color:{Colors.TEXT_SECONDARY};spacing:8px;background:transparent;}}
            QCheckBox::indicator{{width:18px;height:18px;border:2px solid {Colors.TEXT_DIM};border-radius:4px;background:transparent;}}
            QCheckBox::indicator:checked{{background:{Colors.PRIMARY};border-color:{Colors.PRIMARY};}}
        """)
        return cb

    def _combo_style(self):
        return f"QComboBox{{background:{Colors.BG_INPUT};color:{Colors.TEXT_PRIMARY};border:1px solid {Colors.BORDER};border-radius:6px;padding:4px 8px;}}QComboBox::drop-down{{border:none;width:18px;}}QComboBox QAbstractItemView{{background:{Colors.BG_ELEVATED};color:{Colors.TEXT_PRIMARY};selection-background-color:{Colors.PRIMARY};border:1px solid {Colors.BORDER_LIGHT};border-radius:6px;padding:4px;}}"
