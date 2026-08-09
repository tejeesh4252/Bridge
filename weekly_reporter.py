# =============================================================================
# WEEKLY REPORTER - Fixed strict date filtering
# =============================================================================

import os
import csv
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("BridgeBMO.WeeklyReporter")


class WeeklyReporter:
    """
    Reads BMO downloaded CSVs for previous week Mon-Sun.
    Uses LATEST file per account (avoids duplicates).
    Counts ONLY transactions dated within report week.
    """

    def __init__(self, output_base: str):
        self.output_base = output_base
        self.today       = datetime.today().date()

        # ── Previous Mon-Sun ──────────────────────────────────────────
        days_since_monday = self.today.weekday()
        this_monday       = self.today - timedelta(
            days=days_since_monday
        )
        self.week_start   = this_monday - timedelta(days=7)
        self.week_end     = this_monday - timedelta(days=1)

        logger.info(
            f"Weekly period: "
            f"{self.week_start} → {self.week_end}"
        )

    # =========================================================================
    # FOLDER HELPERS
    # =========================================================================
    def _get_week_folders(self) -> list:
        """Return existing dated folders for the week."""
        folders = []
        current = self.week_start
        while current <= self.week_end:
            folder = os.path.join(
                self.output_base,
                current.strftime("%Y-%m-%d")
            )
            if os.path.exists(folder):
                folders.append(
                    (
                        current.strftime("%Y-%m-%d"),
                        folder
                    )
                )
                logger.debug(
                    f"Found: {current.strftime('%Y-%m-%d')}"
                )
            else:
                logger.debug(
                    f"Missing: "
                    f"{current.strftime('%Y-%m-%d')}"
                )
            current += timedelta(days=1)

        logger.info(
            f"Found {len(folders)}/7 week folders"
        )
        return folders

    def _find_latest_csv(
        self, account_number: str
    ) -> str | None:
        """
        Find the LATEST CSV file for an account
        within the report week.
        Searching from latest day backwards.
        """
        folders = self._get_week_folders()
        if not folders:
            return None

        for date_str, folder in reversed(folders):
            for f in sorted(os.listdir(folder)):
                if (f.endswith(".csv") and
                        account_number in f):
                    path = os.path.join(folder, f)
                    logger.debug(
                        f"Latest for {account_number}"
                        f": {date_str}/{f}"
                    )
                    return path
        return None

    # =========================================================================
    # DATE PARSER
    # =========================================================================
    def _parse_date(self, date_str: str):
        """Parse date string to date object."""
        if not date_str:
            return None
        formats = [
            "%Y-%m-%d",    # 2026-07-01 ← BMO standard
            "%m/%d/%Y",    # 07/01/2026
            "%m/%d/%y",    # 07/01/26
            "%d/%m/%Y",    # 01/07/2026
            "%d-%b-%Y",    # 01-Jul-2026
            "%b %d, %Y",   # Jul 01, 2026
        ]
        for fmt in formats:
            try:
                return datetime.strptime(
                    date_str.strip(), fmt
                ).date()
            except ValueError:
                continue
        return None

    # =========================================================================
    # TRANSACTION COUNTER - Strict date filtering
    # =========================================================================
    def _count_week_transactions(
        self, filepath: str
    ) -> dict:
        """
        Count transactions ONLY if dated within
        week_start to week_end inclusive.

        STRICT RULES:
        ✅ Date within week → COUNT
        ❌ Date outside week → SKIP
        ❌ Date unparseable  → SKIP (never guess)
        """
        if not filepath or not os.path.exists(filepath):
            return {
                "count": 0,
                "dates_found": [],
                "skipped": 0
            }

        count       = 0
        dates_found = []
        skipped     = 0

        try:
            with open(
                filepath, newline="",
                encoding="utf-8-sig"
            ) as f:
                all_rows = list(csv.reader(f))

            # Find header row (row starting with "Date")
            header_row_idx = None
            for i, row in enumerate(all_rows):
                if row and str(row[0]).strip() == "Date":
                    header_row_idx = i
                    break

            if header_row_idx is None:
                logger.warning(
                    f"No headers: "
                    f"{os.path.basename(filepath)}"
                )
                return {
                    "count": 0,
                    "dates_found": [],
                    "skipped": 0
                }

            # Count rows strictly within week
            for row in all_rows[header_row_idx + 1:]:
                if not any(row):
                    continue
                if not row[0].strip():
                    continue

                date_str = row[0].strip()
                tx_date  = self._parse_date(date_str)

                if tx_date is None:
                    # Cannot parse → always skip
                    logger.warning(
                        f"Unparseable date: "
                        f"'{date_str}' → SKIPPED"
                    )
                    skipped += 1
                    continue

                if (self.week_start
                        <= tx_date
                        <= self.week_end):
                    count += 1
                    dates_found.append(str(tx_date))
                    logger.debug(
                        f"✅ {tx_date} counted"
                    )
                else:
                    skipped += 1
                    logger.debug(
                        f"❌ {tx_date} outside week"
                    )

            logger.info(
                f"{os.path.basename(filepath)}: "
                f"{count} in week / "
                f"{skipped} outside week"
            )

        except Exception as e:
            logger.error(
                f"Count error: "
                f"{os.path.basename(filepath)}: {e}"
            )

        return {
            "count":       count,
            "dates_found": dates_found,
            "skipped":     skipped,
        }

    # =========================================================================
    # GENERATE SUMMARY
    # =========================================================================
    def generate_summary(self, accounts: list) -> dict:
        """
        Generate weekly transaction count.
        One file per account (latest of the week).
        Strict date filtering within week boundaries.
        """
        logger.info(
            f"Weekly summary: "
            f"{self.week_start} → {self.week_end}"
        )

        week_folders = self._get_week_folders()
        account_data = []
        grand_total  = 0

        for acc in accounts:
            acc_num  = acc["account_number"]
            acc_name = acc["account_name"]

            # LATEST file for this account in the week
            latest_csv = self._find_latest_csv(acc_num)

            if not latest_csv:
                logger.info(
                    f"{acc_num}: No CSV for week"
                )
                account_data.append({
                    "account_number":    acc_num,
                    "account_name":      acc_name,
                    "transaction_count": 0,
                    "days_with_data":    0,
                    "source_file":       "No file",
                })
                continue

            # Count only transactions in week range
            result   = self._count_week_transactions(
                latest_csv
            )
            tx_count = result["count"]

            # How many days had downloads
            days_with_data = sum(
                1 for _, folder in week_folders
                if any(
                    acc_num in f
                    for f in os.listdir(folder)
                    if f.endswith(".csv")
                )
            )

            account_data.append({
                "account_number":    acc_num,
                "account_name":      acc_name,
                "transaction_count": tx_count,
                "days_with_data":    days_with_data,
                "source_file":       os.path.basename(
                    latest_csv
                ),
            })
            grand_total += tx_count

            logger.info(
                f"{acc_num} {acc_name}: "
                f"{tx_count} transactions in week "
                f"({result['skipped']} outside week)"
            )

        return {
            "week_start":    str(self.week_start),
            "week_end":      str(self.week_end),
            "generated_on":  str(self.today),
            "accounts":      account_data,
            "grand_total":   grand_total,
            "folders_found": len(week_folders),
            "folders_total": 7,
        }

    # =========================================================================
    # IS MONDAY
    # =========================================================================
    @staticmethod
    def is_monday() -> bool:
        return datetime.today().weekday() == 0


if __name__ == "__main__":
    print(
        "❌ Do not run this file directly!\n"
        "✅ Run: python main.py"
    )
