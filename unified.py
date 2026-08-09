# unified_app.py
# ── Combined JPM + BMO Extractor GUI (PyQt6) ──────────────────────────────
#
# Runs the two existing engines back to back from ONE credentials screen.
# Does NOT rewrite jpm_navigator.py or the BMO core/ package — it just
# orchestrates them. RSA/OTP still needs a human in the loop for both legs.
#
# Layout: light "Setup" panel on the left (credentials, output folder,
# Run/Stop) — dark "Activity" console on the right (step tracker + live
# log). The step tracker isn't decorative: BMO really does have to finish
# before JPM starts, because two RSA prompts landing at once is exactly
# the failure mode this whole sequential design avoids.

import os
import threading
from datetime import datetime

from PyQt6.QtCore    import Qt, pyqtSignal, QObject
from PyQt6.QtGui     import QFont
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QFrame,
    QDialog, QSizePolicy, QFileDialog, QMessageBox,
)

# ── Existing engines — imported, not modified ─────────────────────────────
from jpm_navigator import run_jpm                      # flat function, own browser
from core.downloader import DownloadOrchestrator        # class-based BMO pipeline
from core.account_loader import load_accounts           # BMO: pulls ALL active accounts
from config import DEFAULT_TIMEFRAME, DEFAULT_OUTPUT_FOLDER

# ── Initialize logging before anything else — same as main.py ────────────
from core.logger_setup import setup_logging
setup_logging()
import logging
logger = logging.getLogger("BridgeBMO.Main")
logger.info("Unified JPM+BMO Extractor starting...")

# ── Palette ────────────────────────────────────────────────────────────────
INK        = "#0f172a"   # console background / primary text
PANEL_BG   = "#f4f6f9"   # left "setup" panel background
CARD_BG    = "#ffffff"
BORDER     = "#e2e8f0"
MUTED      = "#64748b"
TEXT       = "#1e293b"
BMO_ACCENT = "#1a56a0"   # BMO card / badge
JPM_ACCENT = "#334155"   # JPM card / badge (slate, deliberately not blue — reads as
                         # a distinct bank at a glance, not a variation on BMO's color)
GO_COLOR   = "#0f766e"   # Run button — neither bank's color, reads as "start the pipeline"
STOP_COLOR = "#dc2626"
STEP_PENDING_BORDER = "#475569"
STEP_PENDING_TEXT   = "#94a3b8"
STEP_DONE  = "#16a34a"
STEP_ERROR = "#dc2626"


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
        self.setFixedSize(1000, 640)

        self._stop_flag        = threading.Event()
        self._jpm_otp_event    = threading.Event()
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
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Top identity strip (full width) ─────────────────────────────
        strip = QWidget()
        strip.setFixedHeight(50)
        strip.setStyleSheet(f"background-color: {INK};")
        strip_layout = QHBoxLayout(strip)
        strip_layout.setContentsMargins(20, 0, 20, 0)
        title = QLabel("JPM + BMO Extractor")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: white; background: transparent;")
        strip_layout.addWidget(title)
        strip_layout.addStretch()
        root_layout.addWidget(strip)

        # ── Content: left Setup panel / right Activity console ──────────
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._build_setup_panel())
        content_layout.addWidget(self._build_activity_panel())
        root_layout.addWidget(content)

    # ── Left panel: Setup ─────────────────────────────────────────────
    def _build_setup_panel(self):
        panel = QWidget()
        panel.setFixedWidth(380)
        panel.setStyleSheet(f"background-color: {PANEL_BG};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        eyebrow = QLabel("SETUP")
        eyebrow.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        eyebrow.setStyleSheet(f"color: {MUTED}; letter-spacing: 1px;")
        layout.addWidget(eyebrow)

        # Credential cards, ordered to match run order (BMO first, JPM second).
        # Field sets are deliberately NOT the same shape — BMO needs 4 fields
        # (nickname, customer_id, user_id, password), JPM needs 2.
        self._bmo_fields = self._make_cred_card(
            layout, "BMO Credentials", "B", BMO_ACCENT,
            [("Nickname",    "nickname",    False),
             ("Customer ID", "customer_id", False),
             ("User ID",     "user_id",     False),
             ("Password",    "password",    True)],
        )
        self._jpm_fields = self._make_cred_card(
            layout, "JPM Credentials", "J", JPM_ACCENT,
            [("Username", "username", False),
             ("Password", "password", True)],
        )

        # Output folder — pre-filled with config's default (tied to ONE
        # person's Windows username) but overridable per machine. Every
        # teammate running this needs to check/change this before first run.
        out_wrap = QWidget()
        out_wrap.setStyleSheet(f"""
            QWidget {{ background-color: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 8px; }}
        """)
        out_layout = QVBoxLayout(out_wrap)
        out_layout.setContentsMargins(14, 10, 14, 12)
        out_layout.setSpacing(6)
        out_label = QLabel("Output Folder")
        out_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        out_label.setStyleSheet(f"color: {TEXT}; border: none;")
        out_layout.addWidget(out_label)
        out_row = QHBoxLayout()
        out_row.setSpacing(6)
        self._output_folder_field = QLineEdit(DEFAULT_OUTPUT_FOLDER)
        self._output_folder_field.setFont(QFont("Segoe UI", 8))
        self._output_folder_field.setStyleSheet(self._input_style(MUTED))
        out_row.addWidget(self._output_folder_field)
        browse_btn = QPushButton("Browse")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {PANEL_BG}; color: {TEXT}; border: 1px solid {BORDER};
                           border-radius: 4px; padding: 5px 10px; }}
            QPushButton:hover {{ background-color: {BORDER}; }}
        """)
        browse_btn.clicked.connect(self._browse_output_folder)
        out_row.addWidget(browse_btn)
        out_layout.addLayout(out_row)
        layout.addWidget(out_wrap)

        layout.addStretch()

        # ── Run / Stop ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._run_btn = QPushButton("▶   Run Both (BMO → JPM)")
        self._run_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._run_btn.setFixedHeight(38)
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {GO_COLOR}; color: white; border: none; border-radius: 6px; }}
            QPushButton:hover:!disabled {{ background-color: #0d5c56; }}
            QPushButton:disabled {{ background-color: #9db8b5; }}
        """)
        self._run_btn.clicked.connect(self._start)
        btn_row.addWidget(self._run_btn, stretch=3)

        self._stop_btn = QPushButton("⏹  Stop")
        self._stop_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._stop_btn.setFixedHeight(38)
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {STOP_COLOR}; color: white; border: none; border-radius: 6px; }}
            QPushButton:disabled {{ background-color: #f0a0a0; }}
        """)
        self._stop_btn.clicked.connect(self._stop)
        btn_row.addWidget(self._stop_btn, stretch=1)
        layout.addLayout(btn_row)

        self._status_lbl = QLabel("Ready.")
        self._status_lbl.setFont(QFont("Segoe UI", 9))
        self._status_lbl.setStyleSheet(f"color: {MUTED};")
        layout.addWidget(self._status_lbl)

        return panel

    def _input_style(self, accent):
        return f"""
            QLineEdit {{ border: 1px solid {BORDER}; border-radius: 4px; padding: 6px 8px;
                        color: {TEXT}; background: white; }}
            QLineEdit:focus {{ border-color: {accent}; }}
        """

    def _make_cred_card(self, parent_layout, title, badge_text, accent, field_defs):
        card = QWidget()
        card.setStyleSheet(f"""
            QWidget {{ background-color: {CARD_BG}; border: 1px solid {BORDER};
                      border-left: 4px solid {accent}; border-radius: 8px; }}
        """)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(14, 10, 14, 12)
        outer.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        badge = QLabel(badge_text)
        badge.setFixedSize(22, 22)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        badge.setStyleSheet(f"background-color: {accent}; color: white; border: none; border-radius: 11px;")
        header.addWidget(badge)
        head_lbl = QLabel(title)
        head_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        head_lbl.setStyleSheet(f"color: {TEXT}; border: none;")
        header.addWidget(head_lbl)
        header.addStretch()
        outer.addLayout(header)

        # QFormLayout measures the label column from its actual content —
        # no more guessing a fixed pixel width that clips longer labels
        # like "Customer ID" while working fine for "Username".
        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        fields = {}
        for label_text, key, is_pass in field_defs:
            lbl = QLabel(label_text)
            lbl.setFont(QFont("Segoe UI", 9))
            lbl.setStyleSheet(f"color: {MUTED}; border: none;")
            field = QLineEdit()
            field.setFont(QFont("Segoe UI", 9))
            field.setStyleSheet(self._input_style(accent))
            if is_pass:
                field.setEchoMode(QLineEdit.EchoMode.Password)
            form.addRow(lbl, field)
            fields[key] = field
        outer.addLayout(form)

        parent_layout.addWidget(card)
        return fields

    def _browse_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self._output_folder_field.setText(folder)

    # ── Right panel: Activity (step tracker + log console) ─────────────
    def _build_activity_panel(self):
        panel = QWidget()
        panel.setStyleSheet(f"background-color: {INK};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)

        eyebrow = QLabel("ACTIVITY")
        eyebrow.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        eyebrow.setStyleSheet("color: #64748b; letter-spacing: 1px;")
        layout.addWidget(eyebrow)

        # ── Step tracker — reflects the real BMO-then-JPM dependency ───
        tracker = QHBoxLayout()
        tracker.setSpacing(0)
        self._step_bmo_badge, bmo_step = self._make_step("1", "BMO")
        self._step_jpm_badge, jpm_step = self._make_step("2", "JPM")
        tracker.addWidget(bmo_step)
        self._step_line = QFrame()
        self._step_line.setFixedHeight(2)
        self._step_line.setFixedWidth(48)
        self._step_line.setStyleSheet(f"background-color: {STEP_PENDING_BORDER}; border: none;")
        line_wrap = QVBoxLayout()
        line_wrap.addSpacing(11)
        line_wrap.addWidget(self._step_line)
        tracker.addLayout(line_wrap)
        tracker.addWidget(jpm_step)
        tracker.addStretch()
        layout.addLayout(tracker)

        self._log_box = QTextEdit()
        self._log_box.setReadOnly(True)
        self._log_box.setFont(QFont("Consolas", 9))
        self._log_box.setStyleSheet(f"""
            QTextEdit {{ background-color: {INK}; color: #e2e8f0; border: 1px solid #1e293b;
                        border-radius: 6px; padding: 8px; }}
        """)
        self._log_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._log_box)

        return panel

    def _make_step(self, number, label_text):
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        v.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        badge = QLabel(number)
        badge.setFixedSize(24, 24)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        badge.setStyleSheet(self._step_style("pending"))
        v.addWidget(badge, alignment=Qt.AlignmentFlag.AlignHCenter)
        lbl = QLabel(label_text)
        lbl.setFont(QFont("Segoe UI", 8))
        lbl.setStyleSheet("color: #94a3b8;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(lbl)
        return badge, wrap

    def _step_style(self, state):
        if state == "pending":
            return f"background: transparent; color: {STEP_PENDING_TEXT}; border: 2px solid {STEP_PENDING_BORDER}; border-radius: 12px;"
        if state == "active":
            return f"background-color: #2563eb; color: white; border: none; border-radius: 12px;"
        if state == "done":
            return f"background-color: {STEP_DONE}; color: white; border: none; border-radius: 12px;"
        if state == "error":
            return f"background-color: {STEP_ERROR}; color: white; border: none; border-radius: 12px;"
        return ""

    def _set_step(self, bank: str, state: str):
        badge = self._step_bmo_badge if bank == "BMO" else self._step_jpm_badge
        badge.setStyleSheet(self._step_style(state))
        if state == "done":
            badge.setText("✓")
        elif state == "error":
            badge.setText("!")
        else:
            badge.setText("1" if bank == "BMO" else "2")

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
        accent = BMO_ACCENT if bank == "BMO" else JPM_ACCENT
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
        title.setStyleSheet(f"color: {accent};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        body = QLabel("Enter your RSA token in the browser window,\nthen click below to continue.")
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(body)

        confirm_btn = QPushButton("✅   OTP Entered — Continue")
        confirm_btn.setFixedHeight(38)
        confirm_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {accent}; color: white; border: none; border-radius: 4px; }}
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

        output_folder = self._output_folder_field.text().strip()
        if not output_folder:
            self._log("⚠️  Output folder is empty.")
            return
        if not os.path.exists(output_folder):
            answer = QMessageBox.question(
                self, "Folder Not Found",
                f"Output folder does not exist:\n{output_folder}\n\nCreate it now?",
            )
            if answer == QMessageBox.StandardButton.Yes:
                os.makedirs(output_folder, exist_ok=True)
            else:
                self._log("⚠️  Cancelled — output folder does not exist.")
                return

        self._stop_flag.clear()
        self._jpm_otp_event.clear()
        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._status_lbl.setText("Running BMO leg...")
        self._log("▶  Starting combined run — BMO first, then JPM.")
        self._log(f"📁 Output folder: {output_folder}")

        self._set_step("BMO", "active")
        self._set_step("JPM", "pending")

        # No fixed-delay timer for the JPM OTP popup — BMO runs first and
        # takes a variable amount of time, so there's no fixed "8 seconds
        # after Start" moment to guess at anymore. The popup is instead
        # triggered from _run_both() the instant JPM's own login() function
        # logs that it has reached the OTP screen — see show_jpm_otp signal.

        thread = threading.Thread(
            target=self._run_both,
            args=(jpm_user, jpm_pass, bmo_creds, output_folder),
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
    def _run_both(self, jpm_user, jpm_pass, bmo_creds, output_folder):
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
                output_folder=output_folder,
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
                output_folder=output_folder,
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
        self._set_step(bank, "done")
        if bank == "BMO" and not self._stop_flag.is_set():
            self._set_step("JPM", "active")
            self._status_lbl.setText("Running JPM leg...")

    def _on_leg_error(self, bank: str):
        self._log(f"❌ {bank} leg errored — see log above. Continuing to next leg if any.")
        self._set_step(bank, "error")
        if bank == "BMO" and not self._stop_flag.is_set():
            self._set_step("JPM", "active")
            self._status_lbl.setText("Running JPM leg...")

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
