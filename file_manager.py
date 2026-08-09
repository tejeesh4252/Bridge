# =============================================================================
# FILE & LOG MANAGER
# Log sits at ROOT of output folder (persistent across days)
# =============================================================================

import os
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("BridgeBMO.FileManager")


class FileManager:
    """
    Handles output folder creation, download logging,
    and duplicate detection.

    FOLDER STRUCTURE:
    output_base/
    ├── download_log.json   ← ROOT level (persistent)
    ├── logs/               ← Application logs
    ├── 2026-06-30/         ← Dated subfolders
    ├── 2026-07-01/
    └── 2026-07-02/
    """

    def __init__(self, output_base: str):
        self.output_base = output_base
        self.today       = datetime.today().strftime("%Y-%m-%d")

        # ── Log at ROOT (persistent across all days) ──────────────────────
        os.makedirs(output_base, exist_ok=True)
        self.log_path = os.path.join(
            output_base,
            "download_log.json"
        )
        self._log = self._load_log()

    # =========================================================================
    # FOLDER MANAGEMENT
    # =========================================================================
    def ensure_folder(self) -> str:
        """Create today's dated subfolder. Returns its path."""
        today_folder = os.path.join(
            self.output_base, self.today
        )
        os.makedirs(today_folder, exist_ok=True)
        logger.info(f"Today folder: {today_folder}")
        return today_folder

    def get_today_folder(self) -> str:
        return os.path.join(self.output_base, self.today)

    # =========================================================================
    # LOG MANAGEMENT
    # =========================================================================
    def _load_log(self) -> dict:
        """Load existing log from root output folder."""
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, "r") as f:
                    data = json.load(f)
                logger.info(
                    f"Log loaded: {len(data)} entries "
                    f"from {self.log_path}"
                )
                return data
            except Exception as e:
                logger.warning(f"Log load failed: {e}")
                return {}
        logger.info("No existing log - starting fresh")
        return {}

    def _save_log(self):
        """Persist log to root output folder."""
        try:
            with open(self.log_path, "w") as f:
                json.dump(self._log, f, indent=2)
        except Exception as e:
            logger.error(f"Log save failed: {e}")

    def already_downloaded_today(
        self, account_number: str
    ) -> bool:
        """
        True only if successfully downloaded today.
        Errors/partial downloads will be retried.
        """
        key = f"{account_number}_{self.today}"
        status = self._log.get(key, {}).get("status", "")
        return status == "downloaded"

    def log_result(self,
                   account_number:   str,
                   account_name:     str,
                   status:           str,
                   file_path:        str   = None,
                   notes:            str   = "",
                   attempt:          int   = 1,
                   current_balance:  float = None,
                   previous_balance: float = None):
        """
        Record result to persistent JSON log.
        status: downloaded | no_activity | error | skipped
        """
        key = f"{account_number}_{self.today}"
        self._log[key] = {
            "account_number":   account_number,
            "account_name":     account_name,
            "date":             self.today,
            "timestamp":        datetime.now().strftime(
                                    "%Y-%m-%d %H:%M:%S"
                                ),
            "status":           status,
            "file_path":        file_path or "",
            "notes":            notes,
            "attempt":          attempt,
            "current_balance":  current_balance,
            "previous_balance": previous_balance,
        }
        self._save_log()
        logger.info(
            f"Logged [{status}] {account_number} "
            f"{account_name}"
            f"{f' attempt={attempt}' if attempt > 1 else ''}"
        )

    def get_today_summary(self) -> list:
        """All log entries for today."""
        return [
            v for v in self._log.values()
            if v.get("date") == self.today
        ]

    def get_history(self, days: int = 30) -> list:
        """Log entries for last N days."""
        cutoff = (
            datetime.today() - timedelta(days=days)
        ).strftime("%Y-%m-%d")
        return [
            v for v in self._log.values()
            if v.get("date", "") >= cutoff
        ]
