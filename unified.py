# unified_app.py
# ── Combined JPM + BMO Extractor GUI (PyQt6) ──────────────────────────────
#
# Runs the two existing engines back to back from ONE credentials screen.
# Does NOT rewrite jpm_navigator.py or the BMO core/ package — it just
# orchestrates them. See the chat message for the assumptions this makes
# and what it deliberately does not solve (RSA/OTP still needs a human).

import threading
from datetime import datetime

from PyQt6.QtCore    import Qt, pyqtSignal, QObject
from PyQt6.QtGui     import QFont
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QGroupBox, QDialog,
    QSizePolicy,
)

# ── Existing engines — imported, not modified ─────────────────────────────
from jpm_navigator import run_jpm                      # flat function, own browser
from core.downloader import DownloadOrchestrator        # class-based BMO pipeline
from core.account_loader import load_accounts           # BMO: pulls ALL active accounts
from config import DEFAULT_TIMEFRAME, DEFAULT_OUTPUT_FOLDER


# ── Signal bridge (worker thread → GUI thread) ────────────────────────────
class _Signals(QObject):
    log_message   = pyqtSignal(str)
    leg_complete  = pyqtSignal(str)      # "JPM" / "BMO"
    leg_errored   = pyqtSignal(str)
    all_done      = pyqtSignal()
    show_bmo_mfa  = pyqtSignal(object)   # carries the MFAHandler instance
    show_jpm_otp  = pyqtSignal()


class UnifiedApp(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("JPM + BMO Extractor")
        self.setFixedSize(660, 700)

        self._stop_flag       = threading.Event()
        self._jpm_otp_event   = threading.Event()
        self._bmo_orchestrator = None   # set when the BMO leg starts, for Stop

        self._signals = _Signals()
        self._signals.log_message.connect(self._append_log)
        self._signals.leg_complete.connect(self._on_leg_complete)
        self._signals.leg_errored.connect(self._on_leg_error)
        self._signals.all_done.connect(self._on_all_done)
        self._signals.show_bmo_mfa.connect(self._on_show_bmo_mfa)
        self._signals.show_jpm_otp.connect(self._on_show_jpm_otp)

        self._build_ui()

    # ── UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root.setStyleSheet("background-color: white;")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet("background-color: #1a56a0;")
        h_layout = QHBoxLayout(header)
        h_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("🏦  JPM + BMO Extractor")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color: white; background: transparent;")
        h_layout.addWidget(title)
        layout.addWidget(header)

        body = QWidget()
        body.setStyleSheet("background-color: white;")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(10)

        # Two credential cards, ordered to match run order (BMO first, JPM second).
        # Field sets are deliberately NOT the same shape —
        # BMO needs 4 fields (nickname, customer_id, user_id, password), JPM needs 2.
        self._bmo_fields = self._make_cred_card(
            body_layout, "BMO Credentials",
            [("Nickname",    "nickname",    False),
             ("Customer ID", "customer_id", False),
             ("User ID",     "user_id",     False),
             ("Password",    "password",    True)],
        )
        self._jpm_fields = self._make_cred_card(
            body_layout, "JPM Credentials",
            [("Username", "username", False),
             ("Password", "password", True)],
        )

        btn_row = QWidget()
        btn_row.setStyleSheet("background: transparent;")
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)

        self._run_btn = QPushButton("▶   Run Both (BMO → JPM)")
        self._run_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._run_btn.setFixedHeight(36)
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.setStyleSheet("""
            QPushButton { background-color: #1a56a0; color: white; border: none; border-radius: 4px; }
            QPushButton:disabled { background-color: #93afd4; }
        """)
        self._run_btn.clicked.connect(self._start)
        btn_layout.addWidget(self._run_btn)

        self._stop_btn = QPushButton("⏹   Stop")
        self._stop_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._stop_btn.setFixedHeight(36)
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet("""
            QPushButton { background-color: #dc2626; color: white; border: none; border-radius: 4px; }
            QPushButton:disabled { background-color: #f0a0a0; }
        """)
        self._stop_btn.clicked.connect(self._stop)
        btn_layout.addWidget(self._stop_btn)

        body_layout.addWidget(btn_row)

        self._status_lbl = QLabel("Ready.")
        self._status_lbl.setFont(QFont("Segoe UI", 9))
        self._status_lbl.setStyleSheet("color: #6b7280;")
        body_layout.addWidget(self._status_lbl)

        log_group = QGroupBox("  Log  ")
        log_group.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        log_layout = QVBoxLayout(log_group)
        self._log_box = QTextEdit()
        self._log_box.setReadOnly(True)
        self._log_box.setFont(QFont("Consolas", 9))
        self._log_box.setStyleSheet(
            "QTextEdit { background-color: #0f172a; color: #e2e8f0; border: none; border-radius: 4px; }"
        )
        self._log_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        log_layout.addWidget(self._log_box)
        body_layout.addWidget(log_group)

        layout.addWidget(body)

    def _make_cred_card(self, parent_layout, title, field_defs):
        card = QGroupBox(f"  {title}  ")
        card.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        card.setStyleSheet("""
            QGroupBox { border: 1px solid #d1d5db; border-radius: 6px; margin-top: 8px; color: #374151; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(6)
        fields = {}
        for label_text, key, is_pass in field_defs:
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(label_text)
            lbl.setFont(QFont("Segoe UI", 9))
            lbl.setFixedWidth(90)
            row_layout.addWidget(lbl)
            field = QLineEdit()
            field.setFixedWidth(320)
            if is_pass:
                field.setEchoMode(QLineEdit.EchoMode.Password)
            row_layout.addWidget(field)
            row_layout.addStretch()
            card_layout.addWidget(row)
            fields[key] = field
        parent_layout.addWidget(card)
        return fields

    # ── Logging ───────────────────────────────────────────────────────────
    def _append_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_box.append(f"[{ts}]  {msg}")

    def _log(self, msg: str):
        self._append_log(msg)              # main-thread only

    def _safe_log(self, msg: str):
        self._signals.log_message.emit(msg)  # cross-thread safe

    # ── OTP / MFA popup — generic, labeled per bank ─────────────────────
    def _show_mfa_popup(self, bank: str, on_confirm):
        popup = QDialog(self)
        popup.setWindowTitle(f"{bank} — OTP Required")
        popup.setFixedSize(400, 180)
        popup.setWindowFlags(popup.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        popup.setStyleSheet("background-color: white;")
        popup.closeEvent = lambda e: e.ignore()

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QLabel(f"🔐  {bank} RSA Token Required")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #1a56a0;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        body = QLabel("Enter your RSA token in the browser window,\nthen click below to continue.")
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(body)

        confirm_btn = QPushButton("✅   OTP Entered — Continue")
        confirm_btn.setFixedHeight(38)
        confirm_btn.setStyleSheet("""
            QPushButton { background-color: #1a56a0; color: white; border: none; border-radius: 4px; }
        """)

        def on_click():
            on_confirm()
            self._safe_log(f"✅ {bank} OTP confirmed by user.")
            popup.accept()

        confirm_btn.clicked.connect(on_click)
        layout.addWidget(confirm_btn)
        popup.exec()

    def _on_show_bmo_mfa(self, mfa_handler):
        # Runs on the GUI thread (queued via the show_bmo_mfa signal).
        # Orchestrator's worker thread is blocked in mfa_handler.wait_for_mfa()
        # until resume() is called here.
        self._show_mfa_popup("BMO", mfa_handler.resume)

    def _on_show_jpm_otp(self):
        # Runs on the GUI thread. run_jpm()'s worker thread is blocked in
        # wait_for_otp() -> otp_event.wait() until we set the event below.
        self._show_mfa_popup("JPM", self._jpm_otp_event.set)

    # ── Start ─────────────────────────────────────────────────────────────
    def _start(self):
        jpm_user = self._jpm_fields["username"].text().strip()
        jpm_pass = self._jpm_fields["password"].text().strip()
        bmo_creds = {k: f.text().strip() for k, f in self._bmo_fields.items()}

        if not all(bmo_creds.values()):
            self._log("⚠️  Missing one or more BMO fields (nickname / customer ID / user ID / password).")
            return
        if not jpm_user or not jpm_pass:
            self._log("⚠️  Missing JPM username/password.")
            return

        self._stop_flag.clear()
        self._jpm_otp_event.clear()
        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._status_lbl.setText("Running BMO leg...")
        self._log("▶  Starting combined run — BMO first, then JPM.")

        # No fixed-delay timer for the JPM OTP popup — BMO runs first and
        # takes a variable amount of time, so there's no fixed "8 seconds
        # after Start" moment to guess at anymore. The popup is instead
        # triggered from _run_both() the instant JPM's own login() function
        # logs that it has reached the OTP screen — see show_jpm_otp signal.

        thread = threading.Thread(
            target=self._run_both,
            args=(jpm_user, jpm_pass, bmo_creds),
            daemon=True,
        )
        thread.start()

    # ── Worker: BMO then JPM, sequential on purpose ─────────────────────
    # Running both headed browsers at once means two RSA prompts can land
    # near-simultaneously — real risk of missing one or timing out the other
    # mid-token-entry. Sequential trades a few extra minutes for not having
    # that failure mode. If you want speed later, this is the one line to
    # change (spawn two threads instead of calling them one after another) —
    # but do that only after each leg is proven reliable on its own.
    def _run_both(self, jpm_user, jpm_pass, bmo_creds):
        # ── Leg 1: BMO ───────────────────────────────────────────────────
        try:
            self._safe_log("▶ Starting BMO leg...")

            # NOTE: this pulls every ACTIVE account from BMO_Accounts.xlsx —
            # there is no per-run account picker in this combined flow.
            # If you sometimes deselect specific accounts in the current
            # Tkinter app, that behavior is not preserved here yet.
            accounts = load_accounts()

            orchestrator = DownloadOrchestrator(
                credentials=bmo_creds,
                selected_accounts=accounts,
                timeframe=DEFAULT_TIMEFRAME,
                output_folder=DEFAULT_OUTPUT_FOLDER,
                progress_callback=lambda acc, status, msg: self._safe_log(f"[BMO:{acc}] {status}: {msg}"),
                mfa_callback=lambda handler: self._signals.show_bmo_mfa.emit(handler),
                email_enabled=True,
                always_send=True,
            )
            self._bmo_orchestrator = orchestrator
            orchestrator.run()
            self._signals.leg_complete.emit("BMO")
        except Exception as e:
            self._safe_log(f"❌ BMO leg failed: {e}")
            self._signals.leg_errored.emit("BMO")

        if self._stop_flag.is_set():
            self._signals.all_done.emit()
            return

        # ── Leg 2: JPM ───────────────────────────────────────────────────
        try:
            self._safe_log("▶ Starting JPM leg...")
            run_jpm(
                username=jpm_user,
                password=jpm_pass,
                otp_event=self._jpm_otp_event,
                log_callback=self._jpm_log_with_otp_trigger,
                stop_flag=self._stop_flag,
            )
            self._signals.leg_complete.emit("JPM")
        except Exception as e:
            self._safe_log(f"❌ JPM leg failed: {e}")
            self._signals.leg_errored.emit("JPM")

        self._signals.all_done.emit()

    def _jpm_log_with_otp_trigger(self, msg: str):
        """log_callback passed to run_jpm(). Forwards to the log box as
        normal, and additionally pops the OTP dialog the instant
        wait_for_otp() logs that the browser has reached the OTP screen —
        see the matching string in jpm_navigator.py's wait_for_otp()."""
        self._safe_log(msg)
        if "OTP screen" in msg:
            self._signals.show_jpm_otp.emit()

    # ── Stop ──────────────────────────────────────────────────────────────
    def _stop(self):
        self._stop_flag.set()
        self._jpm_otp_event.set()
        if self._bmo_orchestrator:
            self._bmo_orchestrator.stop()
        self._status_lbl.setText("⏹ Stopping — current leg halts at its next checkpoint.")
        self._log("⏹  Stop requested by user.")
        self._stop_btn.setEnabled(False)

    # ── Callbacks ─────────────────────────────────────────────────────────
    def _on_leg_complete(self, bank: str):
        self._log(f"✅ {bank} leg complete.")

    def _on_leg_error(self, bank: str):
        self._log(f"❌ {bank} leg errored — see log above. Continuing to next leg if any.")

    def _on_all_done(self):
        self._status_lbl.setText("✅ Run finished — check log for per-leg results.")
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._bmo_orchestrator = None


if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    win = UnifiedApp()
    win.show()
    sys.exit(app.exec())
