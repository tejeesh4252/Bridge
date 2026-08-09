# jpm_app.py
# ── JPM Extractor GUI (PyQt6) ─────────────────────────────────────────────────

import threading
from datetime import datetime

from PyQt6.QtCore    import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui     import QFont, QColor, QPalette
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QGroupBox, QDialog,
    QSizePolicy, QStatusBar,
)

from jpm_navigator import run_jpm


# ── Signal bridge (thread → GUI) ─────────────────────────────────────────────
class _Signals(QObject):
    log_message = pyqtSignal(str)
    completed   = pyqtSignal()
    errored     = pyqtSignal()


# ── Main GUI App ──────────────────────────────────────────────────────────────
class JPMApp(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("JPM Transaction Extractor")
        self.setFixedSize(620, 580)

        self._stop_flag = threading.Event()
        self._otp_event = threading.Event()

        self._signals = _Signals()
        self._signals.log_message.connect(self._append_log)
        self._signals.completed.connect(self._on_complete)
        self._signals.errored.connect(self._on_error)

        self._build_ui()

    # ── UI Builder ────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root.setStyleSheet("background-color: white;")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet("background-color: #1a56a0;")
        h_layout = QHBoxLayout(header)
        h_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("🏦  JPM Transaction Extractor")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color: white; background: transparent;")
        h_layout.addWidget(title)
        layout.addWidget(header)

        # ── Body ──────────────────────────────────────────────────────────────
        body = QWidget()
        body.setStyleSheet("background-color: white;")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(10)

        # ── Credentials Card ──────────────────────────────────────────────────
        card = QGroupBox("  Credentials  ")
        card.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        card.setStyleSheet("""
            QGroupBox {
                border: 1px solid #d1d5db;
                border-radius: 6px;
                margin-top: 8px;
                color: #374151;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(8)

        self._cred_fields = {}
        for label_text, key, is_pass in [
            ("Username", "username", False),
            ("Password", "password", True),
        ]:
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)

            lbl = QLabel(label_text)
            lbl.setFont(QFont("Segoe UI", 9))
            lbl.setStyleSheet("color: #374151;")
            lbl.setFixedWidth(80)
            row_layout.addWidget(lbl)

            field = QLineEdit()
            field.setFont(QFont("Segoe UI", 9))
            field.setFixedWidth(340)
            field.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #d1d5db;
                    border-radius: 4px;
                    padding: 4px 8px;
                    color: #111827;
                    background: white;
                }
                QLineEdit:focus { border-color: #1a56a0; }
            """)
            if is_pass:
                field.setEchoMode(QLineEdit.EchoMode.Password)
            row_layout.addWidget(field)
            row_layout.addStretch()
            card_layout.addWidget(row)
            self._cred_fields[key] = field

        body_layout.addWidget(card)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QWidget()
        btn_row.setStyleSheet("background: transparent;")
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)

        self._run_btn = QPushButton("▶   Run Extractor")
        self._run_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._run_btn.setFixedHeight(36)
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a56a0;
                color: white;
                border: none;
                border-radius: 4px;
            }
            QPushButton:disabled { background-color: #93afd4; }
            QPushButton:hover:!disabled { background-color: #1648861; }
        """)
        self._run_btn.clicked.connect(self._start)
        btn_layout.addWidget(self._run_btn)

        self._stop_btn = QPushButton("⏹   Stop")
        self._stop_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._stop_btn.setFixedHeight(36)
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc2626;
                color: white;
                border: none;
                border-radius: 4px;
            }
            QPushButton:disabled { background-color: #f0a0a0; }
        """)
        self._stop_btn.clicked.connect(self._stop)
        btn_layout.addWidget(self._stop_btn)

        body_layout.addWidget(btn_row)

        # ── Status Label ──────────────────────────────────────────────────────
        self._status_lbl = QLabel("Ready.")
        self._status_lbl.setFont(QFont("Segoe UI", 9))
        self._status_lbl.setStyleSheet("color: #6b7280;")
        body_layout.addWidget(self._status_lbl)

        # ── Log Window ────────────────────────────────────────────────────────
        log_group = QGroupBox("  Log  ")
        log_group.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        log_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #d1d5db;
                border-radius: 6px;
                margin-top: 8px;
                color: #374151;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
        """)
        log_layout = QVBoxLayout(log_group)

        self._log_box = QTextEdit()
        self._log_box.setReadOnly(True)
        self._log_box.setFont(QFont("Consolas", 9))
        self._log_box.setStyleSheet("""
            QTextEdit {
                background-color: #0f172a;
                color: #e2e8f0;
                border: none;
                border-radius: 4px;
            }
        """)
        self._log_box.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        log_layout.addWidget(self._log_box)
        body_layout.addWidget(log_group)

        layout.addWidget(body)

    # ── Logging ───────────────────────────────────────────────────────────────
    def _append_log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log_box.append(f"[{timestamp}]  {msg}")

    def _log(self, msg: str):
        """Direct call — only from main thread."""
        self._append_log(msg)

    def _safe_log(self, msg: str):
        """Thread-safe — emits signal to main thread."""
        self._signals.log_message.emit(msg)

    # ── OTP Popup ─────────────────────────────────────────────────────────────
    def _show_otp_popup(self):
        popup = QDialog(self)
        popup.setWindowTitle("OTP Required")
        popup.setFixedSize(400, 180)
        popup.setWindowFlags(
            popup.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        popup.setStyleSheet("background-color: white;")

        # Block closing via X button
        popup.closeEvent = lambda e: e.ignore()

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QLabel("🔐  RSA Token Required")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #1a56a0;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        body = QLabel(
            "Please enter your RSA token in the browser.\n"
            "Click the button below once done."
        )
        body.setFont(QFont("Segoe UI", 9))
        body.setStyleSheet("color: #374151;")
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(body)

        confirm_btn = QPushButton("✅   OTP Entered — Continue")
        confirm_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        confirm_btn.setFixedHeight(38)
        confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a56a0;
                color: white;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #164886; }
        """)

        def on_confirm():
            self._otp_event.set()
            self._safe_log("✅ OTP confirmed by user.")
            popup.accept()

        confirm_btn.clicked.connect(on_confirm)
        layout.addWidget(confirm_btn)

        popup.exec()

    # ── Start ─────────────────────────────────────────────────────────────────
    def _start(self):
        username = self._cred_fields["username"].text().strip()
        password = self._cred_fields["password"].text().strip()

        if not username or not password:
            self._log("⚠️  Please enter both Username and Password.")
            return

        self._stop_flag.clear()
        self._otp_event.clear()

        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._status_lbl.setText("Running...")
        self._log("▶  Starting JPM Extractor...")

        # Show OTP popup after 8 s (gives browser time to reach OTP screen)
        QTimer.singleShot(8_000, self._show_otp_popup)

        thread = threading.Thread(
            target=self._run_worker,
            args=(username, password),
            daemon=True,
        )
        thread.start()

    # ── Worker ────────────────────────────────────────────────────────────────
    def _run_worker(self, username: str, password: str):
        try:
            run_jpm(
                username     = username,
                password     = password,
                otp_event    = self._otp_event,
                log_callback = self._safe_log,
                stop_flag    = self._stop_flag,
            )
            self._signals.completed.emit()
        except Exception as e:
            self._safe_log(f"❌ Fatal error: {e}")
            self._signals.errored.emit()

    # ── Stop ──────────────────────────────────────────────────────────────────
    def _stop(self):
        self._stop_flag.set()
        self._otp_event.set()   # Unblock if waiting for OTP
        self._status_lbl.setText("⏹ Stopped by user.")
        self._log("⏹  Stopped by user.")
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

    # ── Completion Callbacks ──────────────────────────────────────────────────
    def _on_complete(self):
        self._status_lbl.setText("✅ Done!")
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

    def _on_error(self):
        self._status_lbl.setText("❌ Error — check log.")
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    win = JPMApp()
    win.show()
    sys.exit(app.exec())
