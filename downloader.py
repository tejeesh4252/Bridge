# =============================================================================
# MAIN DOWNLOAD ORCHESTRATOR
# Updated: Weekly report integration
# =============================================================================

import time
import threading
import logging
from datetime import datetime
from core.browser        import BrowserManager
from core.mfa_handler    import MFAHandler
from core.bmo_navigator  import BMONavigator
from core.file_manager   import FileManager
from core.weekly_reporter import WeeklyReporter
from config              import MAX_RETRIES

logger = logging.getLogger("BridgeBMO.Downloader")


class DownloadOrchestrator:

    def __init__(self,
                 credentials:       dict,
                 selected_accounts: list,
                 timeframe:         str,
                 output_folder:     str,
                 progress_callback,
                 mfa_callback,
                 email_enabled:     bool = True,
                 always_send:       bool = True,
                 excel_path:        str  = "",
                 custom_from:       str  = None,
                 custom_to:         str  = None):

        self.credentials        = credentials
        self.selected_accounts  = selected_accounts
        self.timeframe          = timeframe
        self.output_folder      = output_folder
        self.progress_callback  = progress_callback
        self.mfa_callback       = mfa_callback
        self.email_enabled      = email_enabled
        self.always_send        = always_send
        self.excel_path         = excel_path
        self.custom_from        = custom_from
        self.custom_to          = custom_to
        self._stop_flag         = threading.Event()
        self.mfa_handler        = MFAHandler()

    def stop(self):
        self._stop_flag.set()

    # =========================================================================
    # WEEKEND DETECTION
    # =========================================================================
    def _is_weekend(self) -> bool:
        return datetime.today().weekday() >= 5

    # =========================================================================
    # MAIN RUN
    # =========================================================================
    def run(self):
        """Full download run in background thread."""

        from core.logger_setup import setup_logging
        setup_logging(self.output_folder)

        logger.info("=" * 50)
        logger.info("BMO DOWNLOADER - RUN STARTED")
        logger.info(
            f"Date     : "
            f"{datetime.today().strftime('%Y-%m-%d %A')}"
        )
        logger.info(
            f"Accounts : {len(self.selected_accounts)}"
        )
        logger.info(
            f"Timeframe: {self.timeframe}"
        )
        logger.info("=" * 50)

        if self._is_weekend():
            day = datetime.today().strftime("%A")
            logger.warning(
                f"Running on {day} - "
                f"bank activity unlikely"
            )
            self.progress_callback(
                "SYSTEM", "info",
                f"⚠️  Today is {day}. "
                f"Limited bank activity expected."
            )

        browser      = BrowserManager()
        fm           = FileManager(self.output_folder)
        today_folder = fm.ensure_folder()

        try:
            page = browser.launch()
            nav  = BMONavigator(page, today_folder)

            # ── Login ──────────────────────────────────────────────────
            self.progress_callback(
                "LOGIN", "info",
                "Filling login form..."
            )
            nav.fill_login_form(
                nickname    = self.credentials["nickname"],
                customer_id = self.credentials["customer_id"],
                user_id     = self.credentials["user_id"],
                password    = self.credentials["password"],
            )

            # ── MFA ────────────────────────────────────────────────────
            self.progress_callback(
                "MFA", "waiting",
                "⏸  Waiting for RSA token..."
            )
            self.mfa_callback(self.mfa_handler)
            self.mfa_handler.wait_for_mfa()

            # ── Dashboard ──────────────────────────────────────────────
            self.progress_callback(
                "DASHBOARD", "info",
                "Loading dashboard..."
            )
            nav.wait_for_dashboard()

            # ── Loop accounts ──────────────────────────────────────────
            for account in self.selected_accounts:

                if self._stop_flag.is_set():
                    logger.info("Stop requested")
                    break

                acc_num  = account["account_number"]
                acc_name = account["account_name"]

                if fm.already_downloaded_today(acc_num):
                    self.progress_callback(
                        acc_num, "skipped",
                        "Already downloaded today"
                    )
                    continue

                if not nav.is_session_alive():
                    logger.error("Session expired!")
                    self.progress_callback(
                        "SYSTEM", "error",
                        "❌ Session expired. "
                        "Please re-run."
                    )
                    if self.email_enabled:
                        self._send_error_email(
                            "BMO session expired. "
                            f"Last: {acc_num}"
                        )
                    break

                logger.info(
                    f"Processing: {acc_num} {acc_name}"
                )
                self._process_with_retry(
                    nav, fm, acc_num, acc_name
                )

            # ── Daily Email ────────────────────────────────────────────
            if self.email_enabled:
                self._send_daily_email(fm)

            # ── Weekly Report (Mondays only) ───────────────────────────
            if (self.email_enabled and
                    WeeklyReporter.is_monday()):
                self._send_weekly_report()

        except Exception as e:
            logger.error(
                f"Fatal error: {e}", exc_info=True
            )
            self.progress_callback(
                "SYSTEM", "error",
                f"Fatal error: {str(e)}"
            )
            if self.email_enabled:
                self._send_error_email(str(e))

        finally:
            browser.close()
            self.progress_callback(
                "DONE", "complete",
                "All accounts processed."
            )
            logger.info("Run complete")

    # =========================================================================
    # PROCESS WITH RETRY
    # =========================================================================
    def _process_with_retry(
        self, nav, fm, acc_num, acc_name
    ) -> bool:
        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                logger.info(
                    f"Retry {attempt}/{MAX_RETRIES}: "
                    f"{acc_num}"
                )
                self.progress_callback(
                    acc_num, "processing",
                    f"Retry {attempt}/{MAX_RETRIES}..."
                )
                time.sleep(3)
                try:
                    nav.close_modal()
                except Exception:
                    pass

            result = self._process_account(
                nav, fm, acc_num, acc_name, attempt
            )

            if result in (
                "downloaded", "no_activity", "skipped"
            ):
                return True

            if result == "error" and attempt < MAX_RETRIES:
                continue

        return False

    # =========================================================================
    # PROCESS SINGLE ACCOUNT
    # =========================================================================
    def _process_account(
        self, nav, fm, acc_num, acc_name, attempt=1
    ) -> str:
        self.progress_callback(
            acc_num, "processing",
            "Opening account..."
        )

        if not nav.click_account(acc_num):
            self.progress_callback(
                acc_num, "error",
                f"Account not found (attempt {attempt})"
            )
            fm.log_result(
                acc_num, acc_name, "error",
                notes=f"Link not found (attempt {attempt})",
                attempt=attempt
            )
            return "error"

        self.progress_callback(
            acc_num, "processing",
            f"Applying {self.timeframe} filter..."
        )
        nav.apply_timeframe_filter(
            self.timeframe,
            self.custom_from,
            self.custom_to
        )

        if not nav.has_transactions():
            self.progress_callback(
                acc_num, "no_activity",
                "No transactions in period"
            )
            fm.log_result(
                acc_num, acc_name,
                "no_activity", attempt=attempt
            )
            nav.close_modal()
            return "no_activity"

        self.progress_callback(
            acc_num, "processing",
            "Exporting CSV..."
        )
        file_path = nav.export_csv(acc_num, acc_name)

        if file_path:
            self.progress_callback(
                acc_num, "downloaded",
                "✅ Downloaded successfully"
            )
            fm.log_result(
                acc_num, acc_name,
                "downloaded", file_path,
                attempt=attempt
            )
            nav.close_modal()
            return "downloaded"
        else:
            self.progress_callback(
                acc_num, "error",
                f"Export failed (attempt {attempt})"
            )
            fm.log_result(
                acc_num, acc_name, "error",
                notes=f"Export failed (attempt {attempt})",
                attempt=attempt
            )
            nav.close_modal()
            return "error"

    # =========================================================================
    # DAILY EMAIL
    # =========================================================================
    def _send_daily_email(self, fm: FileManager):
        """Run comparator and send daily summary."""
        try:
            self.progress_callback(
                "EMAIL", "info",
                "Preparing daily email..."
            )

            from core.comparator       import TransactionComparator
            from core.email_sender     import EmailSender
            from core.recipient_loader import load_recipients

            comparator = TransactionComparator(
                self.output_folder
            )
            summary = comparator.compare_all(
                self.selected_accounts
            )

            has_activity = summary["accounts_with_new"] > 0
            if not self.always_send and not has_activity:
                self.progress_callback(
                    "EMAIL", "skipped",
                    "No new activity - email skipped"
                )
                return

            recipients = load_recipients(self.excel_path)
            if not recipients:
                self.progress_callback(
                    "EMAIL", "error",
                    "No recipients found"
                )
                return

            sender  = EmailSender(recipients)
            ok, msg = sender.send_summary(summary)
            self.progress_callback(
                "EMAIL",
                "info" if ok else "error",
                msg
            )
            logger.info(f"Daily email: {msg}")

        except Exception as e:
            logger.error(
                f"Daily email error: {e}", exc_info=True
            )
            self.progress_callback(
                "EMAIL", "error",
                f"Daily email error: {str(e)}"
            )

    # =========================================================================
    # WEEKLY REPORT  ← NEW
    # =========================================================================
    def _send_weekly_report(self):
        """Generate and send Monday weekly report."""
        try:
            self.progress_callback(
                "WEEKLY", "info",
                "📊 Preparing weekly report..."
            )
            logger.info("Generating weekly report...")

            from core.weekly_reporter  import WeeklyReporter
            from core.email_sender     import EmailSender
            from core.recipient_loader import (
                load_weekly_recipients
            )

            # Load weekly-only recipients
            recipients = load_weekly_recipients(
                self.excel_path
            )

            if not recipients:
                self.progress_callback(
                    "WEEKLY", "error",
                    "No weekly recipients found in Excel"
                )
                logger.warning(
                    "No weekly recipients configured"
                )
                return

            logger.info(
                f"Weekly recipients: {recipients}"
            )

            # Generate summary
            reporter = WeeklyReporter(self.output_folder)
            summary  = reporter.generate_summary(
                self.selected_accounts
            )

            # Add output folder to summary for footer
            summary["output_folder"] = self.output_folder

            # Send email
            sender  = EmailSender(recipients)
            ok, msg = sender.send_weekly_report(summary)

            self.progress_callback(
                "WEEKLY",
                "info" if ok else "error",
                msg
            )
            logger.info(f"Weekly report: {msg}")

        except Exception as e:
            logger.error(
                f"Weekly report error: {e}",
                exc_info=True
            )
            self.progress_callback(
                "WEEKLY", "error",
                f"Weekly report error: {str(e)}"
            )

    # =========================================================================
    # ERROR EMAIL
    # =========================================================================
    def _send_error_email(self, error_msg: str):
        """Send error notification if script crashes."""
        try:
            from core.email_sender     import EmailSender
            from core.recipient_loader import load_recipients

            recipients = load_recipients(self.excel_path)
            if not recipients:
                return

            sender = EmailSender(recipients)
            sender.send_error(error_msg)
            logger.info("Error notification sent")

        except Exception as e:
            logger.error(f"Error email failed: {e}")
