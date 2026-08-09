# =============================================================================
# BRIDGE BMO DOWNLOADER - COMPACT SMART GUI v2.0
# =============================================================================

import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from config import TIMEFRAME_OPTIONS, DEFAULT_TIMEFRAME, DEFAULT_OUTPUT_FOLDER
from core.account_loader import (
    load_accounts, validate_excel_format, get_excel_path
)
from core.downloader import DownloadOrchestrator


# =============================================================================
# STATUS STYLING
# =============================================================================
STATUS_COLORS = {
    "downloaded":  "#16a34a",
    "no_activity": "#6b7280",
    "error":       "#dc2626",
    "skipped":     "#d97706",
    "processing":  "#2563eb",
    "waiting":     "#9ca3af",
    "info":        "#1e40af",
    "complete":    "#16a34a",
}

STATUS_ICONS = {
    "downloaded":  "✅",
    "no_activity": "⭕",
    "error":       "❌",
    "skipped":     "⏭",
    "processing":  "🔄",
    "waiting":     "⏳",
    "info":        "ℹ️",
    "complete":    "🏁",
}


# =============================================================================
# MAIN APPLICATION CLASS
# =============================================================================
class BMODownloaderApp:

    def __init__(self, root: tk.Tk):
        self.root             = root
        self.orchestrator     = None
        self._loaded_accounts = []
        self._account_vars    = {}
        self._status_labels   = {}
        self._status_frame    = None
        self._completed       = 0
        self._total           = 0
        self._build_ui()

    # =========================================================================
    # UI CONSTRUCTION
    # =========================================================================
    def _build_ui(self):
        self.root.title("Bridge BMO Downloader  v2.0")
        self.root.geometry("780x700")
        self.root.resizable(True, True)
        self.root.configure(bg="#f1f5f9")

        # ── Compact top bar ───────────────────────────────────────────────
        self._build_topbar()

        # ── Main content - left/right split ──────────────────────────────
        content = tk.Frame(self.root, bg="#f1f5f9")
        content.pack(fill="both", expand=True, padx=10, pady=(6, 6))

        # Left panel - inputs
        left = tk.Frame(content, bg="#f1f5f9")
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))

        # Right panel - accounts + progress
        right = tk.Frame(content, bg="#f1f5f9")
        right.pack(side="right", fill="both", expand=True, padx=(5, 0))

        # ── Left panel sections ───────────────────────────────────────────
        self._build_credentials(left)
        self._build_timeframe(left)
        self._build_output(left)
        self._build_email(left)
        self._build_buttons(left)

        # ── Right panel sections ──────────────────────────────────────────
        self._build_accounts(right)
        self._build_progress(right)

    # =========================================================================
    # TOP BAR - Compact header
    # =========================================================================
    def _build_topbar(self):
        bar = tk.Frame(self.root, bg="#0f3460", pady=8)
        bar.pack(fill="x")

        # Left - title
        tk.Label(
            bar,
            text="🏦  BRIDGE BMO DOWNLOADER",
            font=("Segoe UI", 13, "bold"),
            bg="#0f3460",
            fg="white"
        ).pack(side="left", padx=16)

        # Right - version + date
        tk.Label(
            bar,
            text=f"v2.0  •  {datetime.today().strftime('%B %d, %Y')}",
            font=("Segoe UI", 9),
            bg="#0f3460",
            fg="#93c5fd"
        ).pack(side="right", padx=16)

    # =========================================================================
    # CARD HELPER
    # =========================================================================
    def _card(self, parent: tk.Frame,
              title: str, pady: tuple = (0, 6)) -> tk.Frame:
        """Creates a compact titled card container."""
        outer = tk.Frame(parent, bg="#f1f5f9")
        outer.pack(fill="x", pady=pady)

        # Card title
        tk.Label(
            outer,
            text=title.upper(),
            font=("Segoe UI", 7, "bold"),
            bg="#f1f5f9",
            fg="#64748b",
            anchor="w"
        ).pack(fill="x", padx=2, pady=(0, 2))

        # Card body
        body = tk.Frame(
            outer,
            bg="white",
            relief="flat",
            highlightbackground="#e2e8f0",
            highlightthickness=1
        )
        body.pack(fill="x")

        return body

    # =========================================================================
    # CREDENTIALS
    # =========================================================================
    def _build_credentials(self, parent: tk.Frame):
        body = self._card(parent, "🔐  Credentials")

        self._cred_vars = {}
        fields = [
            ("Nickname",    "nickname",    False, "Tej"),
            ("Customer ID", "customer_id", False, "30xxxx49"),
            ("User ID",     "user_id",     False, "xxxxxxxxxxN"),
            ("Password",    "password",    True,  "••••••••"),
        ]

        for label, key, is_pass, placeholder in fields:
            row = tk.Frame(body, bg="white")
            row.pack(fill="x", padx=10, pady=3)

            tk.Label(
                row,
                text=label,
                font=("Segoe UI", 9),
                bg="white",
                fg="#374151",
                width=12,
                anchor="w"
            ).pack(side="left")

            var = tk.StringVar()
            entry = ttk.Entry(
                row,
                textvariable=var,
                width=28,
                show="●" if is_pass else "",
                font=("Segoe UI", 9)
            )
            entry.pack(side="left", padx=(4, 0))
            self._cred_vars[key] = var

        # RSA note - compact
        note = tk.Frame(body, bg="#fefce8")
        note.pack(fill="x", padx=0, pady=(4, 0))
        tk.Label(
            note,
            text="⚠  RSA Token entered manually in browser",
            font=("Segoe UI", 8, "italic"),
            bg="#fefce8",
            fg="#92400e",
            anchor="w",
            padx=10,
            pady=4
        ).pack(fill="x")

    # =========================================================================
    # TIMEFRAME
    # =========================================================================
    def _build_timeframe(self, parent: tk.Frame):
        body = self._card(parent, "📅  Timeframe")

        self._timeframe_var = tk.StringVar(value=DEFAULT_TIMEFRAME)

        btn_row = tk.Frame(body, bg="white")
        btn_row.pack(fill="x", padx=8, pady=6)

        for opt in TIMEFRAME_OPTIONS:
            tk.Radiobutton(
                btn_row,
                text=opt,
                variable=self._timeframe_var,
                value=opt,
                font=("Segoe UI", 8),
                bg="white",
                fg="#374151",
                activebackground="white",
                command=self._toggle_custom
            ).pack(side="left", padx=3)

        # Custom dates - hidden by default
        self._custom_frame = tk.Frame(body, bg="white")

        tk.Label(
            self._custom_frame,
            text="From",
            font=("Segoe UI", 8),
            bg="white"
        ).pack(side="left", padx=(10, 2))

        self._custom_from = tk.StringVar(
            value=datetime.today().strftime("%Y-%m-%d")
        )
        ttk.Entry(
            self._custom_frame,
            textvariable=self._custom_from,
            width=12,
            font=("Segoe UI", 8)
        ).pack(side="left")

        tk.Label(
            self._custom_frame,
            text="To",
            font=("Segoe UI", 8),
            bg="white"
        ).pack(side="left", padx=(8, 2))

        self._custom_to = tk.StringVar(
            value=datetime.today().strftime("%Y-%m-%d")
        )
        ttk.Entry(
            self._custom_frame,
            textvariable=self._custom_to,
            width=12,
            font=("Segoe UI", 8)
        ).pack(side="left", padx=(0, 10))

        self._custom_frame.pack_forget()

    def _toggle_custom(self):
        if self._timeframe_var.get() == "Custom":
            self._custom_frame.pack(fill="x", pady=(0, 6))
        else:
            self._custom_frame.pack_forget()

    # =========================================================================
    # OUTPUT FOLDER
    # =========================================================================
    def _build_output(self, parent: tk.Frame):
        body = self._card(parent, "📁  Output Folder")

        row = tk.Frame(body, bg="white")
        row.pack(fill="x", padx=8, pady=6)

        self._output_folder = tk.StringVar(
            value=DEFAULT_OUTPUT_FOLDER
        )

        ttk.Entry(
            row,
            textvariable=self._output_folder,
            width=36,
            font=("Segoe UI", 8)
        ).pack(side="left")

        ttk.Button(
            row,
            text="Browse",
            command=self._browse_output,
            width=8
        ).pack(side="left", padx=(6, 0))

    def _browse_output(self):
        folder = filedialog.askdirectory(
            title="Select Output Folder"
        )
        if folder:
            self._output_folder.set(folder)

    # =========================================================================
    # EMAIL
    # =========================================================================
    def _build_email(self, parent: tk.Frame):
        body = self._card(parent, "📧  Email Notification")

        top = tk.Frame(body, bg="white")
        top.pack(fill="x", padx=8, pady=(6, 2))

        self._email_enabled = tk.BooleanVar(value=True)
        tk.Checkbutton(
            top,
            text="Send summary email via Outlook after download",
            variable=self._email_enabled,
            font=("Segoe UI", 9),
            bg="white",
            fg="#374151",
            activebackground="white",
            command=self._toggle_email
        ).pack(anchor="w")

        self._email_sub = tk.Frame(body, bg="white")
        self._email_sub.pack(fill="x", padx=8, pady=(0, 6))

        self._always_send = tk.BooleanVar(value=True)
        tk.Checkbutton(
            self._email_sub,
            text="Send even when no new activity",
            variable=self._always_send,
            font=("Segoe UI", 8),
            bg="white",
            fg="#6b7280",
            activebackground="white"
        ).pack(anchor="w")

        tk.Label(
            self._email_sub,
            text="Recipients → BMO_Accounts.xlsx  →  Recipients sheet",
            font=("Segoe UI", 8, "italic"),
            bg="white",
            fg="#1a56a0"
        ).pack(anchor="w", pady=(2, 0))

    def _toggle_email(self):
        if self._email_enabled.get():
            self._email_sub.pack(fill="x", padx=8, pady=(0, 6))
        else:
            self._email_sub.pack_forget()

    # =========================================================================
    # ACTION BUTTONS
    # =========================================================================
    def _build_buttons(self, parent: tk.Frame):
        frame = tk.Frame(parent, bg="#f1f5f9")
        frame.pack(fill="x", pady=(4, 0))

        self._start_btn = tk.Button(
            frame,
            text="▶   START DOWNLOAD",
            font=("Segoe UI", 11, "bold"),
            bg="#1a56a0",
            fg="white",
            relief="flat",
            pady=8,
            cursor="hand2",
            command=self._start_download
        )
        self._start_btn.pack(fill="x")

        self._stop_btn = tk.Button(
            frame,
            text="⏹   STOP",
            font=("Segoe UI", 9),
            bg="#dc2626",
            fg="white",
            relief="flat",
            pady=5,
            cursor="hand2",
            command=self._stop_download,
            state="disabled"
        )
        self._stop_btn.pack(fill="x", pady=(4, 0))

    # =========================================================================
    # ACCOUNTS - RIGHT PANEL
    # =========================================================================
    def _build_accounts(self, parent: tk.Frame):
        outer = tk.Frame(parent, bg="#f1f5f9")
        outer.pack(fill="both", expand=True, pady=(0, 6))

        # Title row with buttons
        title_row = tk.Frame(outer, bg="#f1f5f9")
        title_row.pack(fill="x", pady=(0, 2))

        tk.Label(
            title_row,
            text="ACCOUNTS",
            font=("Segoe UI", 7, "bold"),
            bg="#f1f5f9",
            fg="#64748b"
        ).pack(side="left", padx=2)

        # Reload + browse buttons
        ttk.Button(
            title_row,
            text="🔄",
            command=self._reload_accounts,
            width=3
        ).pack(side="right", padx=(2, 0))

        ttk.Button(
            title_row,
            text="Browse",
            command=self._browse_excel,
            width=7
        ).pack(side="right", padx=2)

        ttk.Button(
            title_row,
            text="None",
            command=self._deselect_all,
            width=5
        ).pack(side="right", padx=2)

        ttk.Button(
            title_row,
            text="All",
            command=self._select_all,
            width=4
        ).pack(side="right", padx=2)

        # Excel path - compact
        path_frame = tk.Frame(
            outer, bg="white",
            highlightbackground="#e2e8f0",
            highlightthickness=1
        )
        path_frame.pack(fill="x", pady=(0, 4))

        self._excel_path_var = tk.StringVar(value=get_excel_path())
        tk.Label(
            path_frame,
            textvariable=self._excel_path_var,
            font=("Segoe UI", 7),
            bg="white",
            fg="#64748b",
            anchor="w",
            wraplength=340
        ).pack(fill="x", padx=6, pady=3)

        # Status label
        self._excel_status_lbl = tk.Label(
            outer,
            text="",
            font=("Segoe UI", 8, "italic"),
            bg="#f1f5f9",
            anchor="w"
        )
        self._excel_status_lbl.pack(
            fill="x", padx=2, pady=(0, 2)
        )

        # Scrollable checkbox list
        list_body = tk.Frame(
            outer, bg="white",
            highlightbackground="#e2e8f0",
            highlightthickness=1
        )
        list_body.pack(fill="both", expand=True)

        list_canvas = tk.Canvas(
            list_body, bg="white",
            highlightthickness=0
        )
        list_scroll = ttk.Scrollbar(
            list_body,
            orient="vertical",
            command=list_canvas.yview
        )
        self._accounts_inner = tk.Frame(list_canvas, bg="white")

        self._accounts_inner.bind(
            "<Configure>",
            lambda e: list_canvas.configure(
                scrollregion=list_canvas.bbox("all")
            )
        )

        list_canvas.create_window(
            (0, 0),
            window=self._accounts_inner,
            anchor="nw"
        )
        list_canvas.configure(yscrollcommand=list_scroll.set)
        list_canvas.pack(side="left", fill="both", expand=True)
        list_scroll.pack(side="right", fill="y")

        # Mouse wheel
        list_canvas.bind_all(
            "<MouseWheel>",
            lambda e: list_canvas.yview_scroll(
                int(-1 * (e.delta / 120)), "units"
            )
        )

        self._reload_accounts()

    # -------------------------------------------------------------------------
    def _browse_excel(self):
        path = filedialog.askopenfilename(
            title="Select Account List Excel File",
            filetypes=[
                ("Excel Files", "*.xlsx *.xls"),
                ("All Files",   "*.*")
            ]
        )
        if path:
            self._excel_path_var.set(path)
            self._reload_accounts()

    # -------------------------------------------------------------------------
    def _reload_accounts(self):
        excel_path = self._excel_path_var.get().strip()
        is_valid, message = validate_excel_format(excel_path)

        self._excel_status_lbl.config(
            text=message,
            fg="#16a34a" if is_valid else "#dc2626"
        )

        for widget in self._accounts_inner.winfo_children():
            widget.destroy()
        self._account_vars.clear()
        self._loaded_accounts.clear()

        if not is_valid:
            tk.Label(
                self._accounts_inner,
                text="⚠️  Fix Excel errors above.",
                font=("Segoe UI", 8, "italic"),
                bg="white",
                fg="#dc2626"
            ).pack(padx=8, pady=8)
            return

        try:
            accounts = load_accounts(excel_path)
            self._loaded_accounts = accounts

            for i, acc in enumerate(accounts):
                var    = tk.BooleanVar(value=True)
                row_bg = "#f8fafc" if i % 2 == 0 else "white"
                row    = tk.Frame(
                    self._accounts_inner, bg=row_bg
                )
                row.pack(fill="x")

                tk.Checkbutton(
                    row,
                    text=(
                        f"  {acc['account_number']}"
                        f"   {acc['account_name']}"
                    ),
                    variable=var,
                    font=("Segoe UI", 8),
                    bg=row_bg,
                    fg="#374151",
                    activebackground=row_bg,
                    anchor="w"
                ).pack(
                    side="left", fill="x",
                    padx=4, pady=1
                )
                self._account_vars[acc["account_number"]] = var

            self._rebuild_status_labels(accounts)

        except Exception as e:
            tk.Label(
                self._accounts_inner,
                text=f"Error: {e}",
                font=("Segoe UI", 8),
                bg="white",
                fg="#dc2626"
            ).pack(padx=8, pady=8)

    # -------------------------------------------------------------------------
    def _select_all(self):
        for var in self._account_vars.values():
            var.set(True)

    def _deselect_all(self):
        for var in self._account_vars.values():
            var.set(False)

    # =========================================================================
    # PROGRESS - RIGHT PANEL BOTTOM
    # =========================================================================
    def _build_progress(self, parent: tk.Frame):
        outer = tk.Frame(parent, bg="#f1f5f9")
        outer.pack(fill="x", pady=(0, 0))

        tk.Label(
            outer,
            text="PROGRESS",
            font=("Segoe UI", 7, "bold"),
            bg="#f1f5f9",
            fg="#64748b",
            anchor="w"
        ).pack(fill="x", padx=2, pady=(0, 2))

        progress_body = tk.Frame(
            outer, bg="white",
            highlightbackground="#e2e8f0",
            highlightthickness=1
        )
        progress_body.pack(fill="x")

        # Progress bar
        self._progress_var = tk.DoubleVar()
        self._progress_bar = ttk.Progressbar(
            progress_body,
            variable=self._progress_var,
            maximum=100
        )
        self._progress_bar.pack(
            fill="x", padx=8, pady=(6, 2)
        )

        # Progress label
        self._progress_label = tk.Label(
            progress_body,
            text="Ready to start...",
            font=("Segoe UI", 8),
            bg="white",
            fg="#6b7280",
            anchor="w"
        )
        self._progress_label.pack(
            anchor="w", padx=8, pady=(0, 6)
        )

        # Per-account status
        self._status_frame = tk.Frame(
            outer, bg="white",
            highlightbackground="#e2e8f0",
            highlightthickness=1
        )
        self._status_frame.pack(fill="x", pady=(4, 0))

    # -------------------------------------------------------------------------
    def _rebuild_status_labels(self, accounts: list):
        if self._status_frame is None:
            return

        for widget in self._status_frame.winfo_children():
            widget.destroy()
        self._status_labels.clear()

        for acc in accounts:
            row = tk.Frame(self._status_frame, bg="white")
            row.pack(fill="x", padx=6, pady=1)

            lbl = tk.Label(
                row,
                text=(
                    f"⏳  {acc['account_number']}"
                    f"  {acc['account_name']}"
                ),
                font=("Segoe UI", 8),
                bg="white",
                fg="#9ca3af",
                anchor="w"
            )
            lbl.pack(side="left")
            self._status_labels[acc["account_number"]] = lbl

    # =========================================================================
    # MFA POPUP
    # =========================================================================
    def _show_mfa_popup(self, mfa_handler):
        self.root.after(0, self._open_mfa_dialog, mfa_handler)

    def _open_mfa_dialog(self, mfa_handler):
        dialog = tk.Toplevel(self.root)
        dialog.title("RSA Token Required")
        dialog.geometry("420x190")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        dialog.grab_set()
        dialog.configure(bg="white")

        tk.Label(
            dialog,
            text="⏸   RSA Token Required",
            font=("Segoe UI", 13, "bold"),
            fg="#1a56a0",
            bg="white"
        ).pack(pady=(20, 6))

        tk.Label(
            dialog,
            text=(
                "Enter your RSA token in the browser window.\n"
                "Click Continue once fully logged in."
            ),
            font=("Segoe UI", 9),
            bg="white",
            fg="#374151",
            wraplength=380,
            justify="center"
        ).pack(pady=(0, 16))

        def on_continue():
            mfa_handler.resume()
            dialog.destroy()

        tk.Button(
            dialog,
            text="✅   I've Completed MFA — Continue",
            font=("Segoe UI", 10, "bold"),
            bg="#1a56a0",
            fg="white",
            relief="flat",
            pady=8,
            cursor="hand2",
            command=on_continue,
            width=34
        ).pack()

        dialog.protocol("WM_DELETE_WINDOW", lambda: None)

    # =========================================================================
    # DOWNLOAD CONTROL
    # =========================================================================
    def _get_selected_accounts(self) -> list:
        return [
            acc for acc in self._loaded_accounts
            if self._account_vars.get(
                acc["account_number"], tk.BooleanVar()
            ).get()
        ]

    # -------------------------------------------------------------------------
    def _validate_inputs(self) -> bool:
        creds = {
            k: v.get().strip()
            for k, v in self._cred_vars.items()
        }
        if not all(creds.values()):
            messagebox.showerror(
                "Missing Credentials",
                "Please fill in all credential fields."
            )
            return False

        if not self._get_selected_accounts():
            messagebox.showerror(
                "No Accounts",
                "Please select at least one account."
            )
            return False

        if not self._output_folder.get().strip():
            messagebox.showerror(
                "No Output Folder",
                "Please select an output folder."
            )
            return False

        if not os.path.exists(self._output_folder.get().strip()):
            answer = messagebox.askyesno(
                "Folder Not Found",
                f"Output folder does not exist:\n"
                f"{self._output_folder.get()}\n\n"
                f"Create it now?"
            )
            if answer:
                os.makedirs(
                    self._output_folder.get(), exist_ok=True
                )
            else:
                return False

        return True

    # -------------------------------------------------------------------------
    def _start_download(self):
        if not self._validate_inputs():
            return

        self._start_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._reset_progress()

        credentials     = {
            k: v.get() for k, v in self._cred_vars.items()
        }
        selected        = self._get_selected_accounts()
        self._total     = len(selected)
        self._completed = 0

        custom_from = (
            self._custom_from.get()
            if self._timeframe_var.get() == "Custom" else None
        )
        custom_to = (
            self._custom_to.get()
            if self._timeframe_var.get() == "Custom" else None
        )

        self.orchestrator = DownloadOrchestrator(
            credentials       = credentials,
            selected_accounts = selected,
            timeframe         = self._timeframe_var.get(),
            output_folder     = self._output_folder.get(),
            progress_callback = self._on_progress,
            mfa_callback      = self._show_mfa_popup,
            email_enabled     = self._email_enabled.get(),
            always_send       = self._always_send.get(),
            excel_path        = self._excel_path_var.get(),
            custom_from       = custom_from,
            custom_to         = custom_to,
        )

        thread = threading.Thread(
            target=self.orchestrator.run,
            daemon=True
        )
        thread.start()

    # -------------------------------------------------------------------------
    def _stop_download(self):
        if self.orchestrator:
            self.orchestrator.stop()
        self._stop_btn.config(state="disabled")
        self._progress_label.config(
            text="⏹  Stopped by user."
        )

    # -------------------------------------------------------------------------
    def _reset_progress(self):
        self._progress_var.set(0)
        self._progress_label.config(text="Starting...")

        for acc in self._loaded_accounts:
            lbl = self._status_labels.get(acc["account_number"])
            if lbl:
                lbl.config(
                    text=(
                        f"⏳  {acc['account_number']}"
                        f"  {acc['account_name']}"
                    ),
                    fg="#9ca3af"
                )

    # =========================================================================
    # PROGRESS CALLBACK
    # =========================================================================
    def _on_progress(self, account_number: str,
                     status: str, message: str):
        self.root.after(
            0, self._update_ui,
            account_number, status, message
        )

    # -------------------------------------------------------------------------
    def _update_ui(self, account_number: str,
                   status: str, message: str):
        icon  = STATUS_ICONS.get(status, "•")
        color = STATUS_COLORS.get(status, "#111827")

        if status == "waiting":
            self._progress_label.config(
                text="⏸  Waiting for RSA token..."
            )
            return

        lbl = self._status_labels.get(account_number)
        if lbl:
            acc_name = next(
                (
                    a["account_name"]
                    for a in self._loaded_accounts
                    if a["account_number"] == account_number
                ), ""
            )
            lbl.config(
                text=(
                    f"{icon}  {account_number}"
                    f"  {acc_name}  —  {message}"
                ),
                fg=color
            )

            terminal = {
                "downloaded", "no_activity",
                "error",      "skipped"
            }
            if status in terminal:
                self._completed += 1
                pct = (self._completed / self._total) * 100
                self._progress_var.set(pct)
                self._progress_label.config(
                    text=(
                        f"{self._completed} / {self._total}"
                        f"  accounts processed"
                    )
                )

        if status == "complete":
            self._progress_var.set(100)
            self._progress_label.config(
                text="🏁  All done!"
            )
            self._start_btn.config(state="normal")
            self._stop_btn.config(state="disabled")

            downloaded = sum(
                1 for a in self._loaded_accounts
                if self._status_labels.get(a["account_number"])
                and "✅" in self._status_labels[
                    a["account_number"]
                ].cget("text")
            )

            messagebox.showinfo(
                "Complete",
                f"✅  {self._total} accounts processed\n"
                f"📥  {downloaded} files downloaded\n\n"
                f"📁  {self._output_folder.get()}"
            )


# =============================================================================
# ENTRY POINT
# =============================================================================
def main():
    root = tk.Tk()

    # ── Style ─────────────────────────────────────────────────────────────
    style = ttk.Style()
    style.theme_use("clam")
    style.configure(
        "TButton",
        font=("Segoe UI", 9),
        relief="flat"
    )
    style.configure(
        "TEntry",
        fieldbackground="white",
        relief="flat"
    )
    style.configure(
        "Horizontal.TProgressbar",
        troughcolor="#e2e8f0",
        background="#1a56a0",
        thickness=8
    )

    app = BMODownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
