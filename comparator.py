# =============================================================================
# TRANSACTION COMPARATOR - Built for BMO CSV Format
# Updated: Tighter date-based detection logic
#          No bleed-through from previous days
# =============================================================================

import os
import csv
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("BridgeBMO.Comparator")


class TransactionComparator:
    """
    Reads BMO downloaded CSV files.

    BMO CSV format:
    - Rows 1-5 : Account metadata + balance info
    - Row 6    : Empty separator
    - Row 7    : Headers (Date|Type|Description|Debit|Credit)
    - Row 8+   : Transaction data

    Detection Rules:
    - Transaction dated TODAY     → ALWAYS new
    - Transaction dated YESTERDAY → New only if not in
                                    yesterday's file
    - Transaction older than 2 days → NOT new
                                      (already captured)
    """

    def __init__(self, output_base: str):
        self.output_base  = output_base
        self.today        = datetime.today().strftime(
            "%Y-%m-%d"
        )
        self.yesterday    = (
            datetime.today() - timedelta(days=1)
        ).strftime("%Y-%m-%d")
        self.today_dt     = datetime.today().date()
        self.yesterday_dt = (
            datetime.today() - timedelta(days=1)
        ).date()

    # =========================================================================
    # FOLDER & FILE HELPERS
    # =========================================================================
    def _get_folder(self, date_str: str) -> str:
        return os.path.join(self.output_base, date_str)

    def _find_csv(self, folder: str,
                  account_number: str) -> str | None:
        """Find CSV file for account in folder."""
        if not os.path.exists(folder):
            return None
        for f in os.listdir(folder):
            if f.endswith(".csv") and account_number in f:
                return os.path.join(folder, f)
        return None

    # =========================================================================
    # BMO CSV PARSER
    # =========================================================================
    def _parse_bmo_csv(self, filepath: str) -> dict:
        """
        Parse BMO CSV into metadata + transactions.

        BMO CSV Structure:
        Row 0 : Account Name  | value | Curr Avail Bal | value
        Row 1 : Account Number| value | Curr Ledger Bal| value
        Row 2 : Account Type  | value | Prev Day Avail | value
        Row 3 : (blank)       |       | Prev Day Bal   | value
        Row 4 : (blank)       |       | Currency       | value
        Row 5 : (empty line)
        Row 6 : Date | Transaction Type | Desc | Debit | Credit
        Row 7+: transaction data rows
        """
        result = {
            "metadata":     {},
            "transactions": [],
            "error":        None,
        }

        if not filepath or not os.path.exists(filepath):
            result["error"] = "File not found"
            return result

        try:
            with open(
                filepath, newline="", encoding="utf-8-sig"
            ) as f:
                all_rows = list(csv.reader(f))

            # ── Extract metadata from rows 0-4 ───────────────────────
            metadata = {}
            for row in all_rows[:5]:
                if not any(row):
                    continue
                # Left side (col 0 = key, col 1 = value)
                if len(row) > 1 and row[0].strip():
                    metadata[row[0].strip()] = \
                        row[1].strip()
                # Right side (col 2 = key, col 3 = value)
                if len(row) > 3 and row[2].strip():
                    metadata[row[2].strip()] = \
                        row[3].strip()
            result["metadata"] = metadata

            # ── Find real header row ──────────────────────────────────
            header_row_idx = None
            for i, row in enumerate(all_rows):
                if row and str(row[0]).strip() == "Date":
                    header_row_idx = i
                    break

            if header_row_idx is None:
                result["error"] = "Transaction headers not found"
                return result

            # ── Extract headers ───────────────────────────────────────
            headers = [
                str(h).strip()
                for h in all_rows[header_row_idx]
                if h is not None
            ]
            logger.debug(f"Headers: {headers}")

            # ── Extract transactions ──────────────────────────────────
            transactions = []
            for row in all_rows[header_row_idx + 1:]:
                if not any(row):
                    continue
                if len(row) < 2:
                    continue
                if not str(row[0]).strip():
                    continue

                tx = {}
                for i, header in enumerate(headers):
                    tx[header] = (
                        str(row[i]).strip()
                        if i < len(row) and
                        row[i] is not None
                        else ""
                    )
                transactions.append(tx)

            result["transactions"] = transactions
            logger.info(
                f"Parsed {len(transactions)} transactions "
                f"from {os.path.basename(filepath)}"
            )

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Parse error: {e}")

        return result

    # =========================================================================
    # BALANCE EXTRACTOR
    # =========================================================================
    def _extract_balances(self, metadata: dict) -> dict:
        """Extract and clean balance values from metadata."""
        def clean(val: str) -> float:
            try:
                return float(
                    val.replace(",", "")
                       .replace("$", "")
                       .replace(" ", "")
                )
            except (ValueError, AttributeError):
                return 0.0

        return {
            "current_available":  clean(
                metadata.get(
                    "Current Available Balance", "0"
                )
            ),
            "current_ledger":     clean(
                metadata.get(
                    "Current Ledger Balance", "0"
                )
            ),
            "previous_available": clean(
                metadata.get(
                    "Previous Day Available", "0"
                )
            ),
            "previous_ledger":    clean(
                metadata.get(
                    "Previous Day Balance", "0"
                )
            ),
            "currency": metadata.get("Currency", "USD"),
        }

    # =========================================================================
    # AMOUNT PARSER
    # =========================================================================
    def _parse_amount(self, amount_str: str) -> float:
        """Parse '4,150.57' or '(4,150.57)' → float."""
        if not amount_str or not amount_str.strip():
            return 0.0
        try:
            cleaned = (
                amount_str
                .replace(",", "")
                .replace("$", "")
                .replace(" ", "")
                .replace("(", "-")
                .replace(")", "")
                .strip()
            )
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

    # =========================================================================
    # DATE PARSER
    # =========================================================================
    def _parse_tx_date(self, date_str: str):
        """
        Parse transaction date string to date object.
        Handles multiple BMO date formats.
        Returns date object or None if unparseable.
        """
        if not date_str:
            return None

        formats = [
            "%Y-%m-%d",    # 2026-07-01  ← BMO standard
            "%m/%d/%Y",    # 07/01/2026
            "%m/%d/%y",    # 07/01/26
            "%d/%m/%Y",    # 01/07/2026
            "%b %d, %Y",   # Jul 01, 2026
            "%B %d, %Y",   # July 01, 2026
            "%d-%b-%Y",    # 01-Jul-2026
        ]
        for fmt in formats:
            try:
                return datetime.strptime(
                    date_str.strip(), fmt
                ).date()
            except ValueError:
                continue
        return None

    def _is_today(self, date_str: str) -> bool:
        """Check if date string represents today."""
        parsed = self._parse_tx_date(date_str)
        if not parsed:
            return False
        return parsed == self.today_dt

    # =========================================================================
    # TRANSACTION UNIQUE KEY
    # =========================================================================
    def _make_tx_key(self, tx: dict) -> str:
        """
        Unique key per transaction.
        Date + Amount + first 40 chars of Description.
        Used to detect duplicate transactions between days.
        """
        date   = tx.get("Date",        "")
        debit  = tx.get("Debit",       "")
        credit = tx.get("Credit",      "")
        desc   = tx.get("Description", "")[:40]
        amount = debit if debit else credit
        return f"{date}|{amount}|{desc}"

    # =========================================================================
    # NEW TRANSACTION DETECTION  ← CORE UPDATED LOGIC
    # =========================================================================
    def _find_new_transactions(
        self,
        today_rows:     list,
        yesterday_keys: set,
    ) -> tuple:
        """
        Identify genuinely new transactions.

        DETECTION RULES:
        ┌─────────────────────────────────────────────────┐
        │ TX Date = TODAY     → ALWAYS new                │
        │ TX Date = YESTERDAY → New ONLY if not in        │
        │                       yesterday's file          │
        │ TX Date = Older     → NOT new                   │
        │                       (already reported)        │
        │ TX Date = Unknown   → Fallback to key check     │
        └─────────────────────────────────────────────────┘

        Returns: (new_transactions, all_transactions)
        """
        new_transactions = []
        all_transactions = []

        for tx in today_rows:
            date_str = tx.get("Date", "")
            debit    = self._parse_amount(
                tx.get("Debit",  "")
            )
            credit   = self._parse_amount(
                tx.get("Credit", "")
            )
            tx_key   = self._make_tx_key(tx)
            tx_date  = self._parse_tx_date(date_str)

            # ── Determine if NEW ──────────────────────────────────────
            is_new    = False
            date_flag = ""

            if tx_date is not None:
                if tx_date == self.today_dt:
                    # TODAY → always new regardless of anything
                    is_new    = True
                    date_flag = "today"

                elif tx_date == self.yesterday_dt:
                    # YESTERDAY → new only if missing from
                    # yesterday's downloaded file
                    is_new    = tx_key not in yesterday_keys
                    date_flag = "yesterday"

                else:
                    # OLDER → not new, skip
                    is_new    = False
                    date_flag = "historical"

            else:
                # Cannot parse date → safe fallback
                is_new    = tx_key not in yesterday_keys
                date_flag = "unknown"

            logger.debug(
                f"TX [{date_flag}] {date_str} "
                f"{'NEW' if is_new else 'OLD'} "
                f"key={tx_key[:30]}"
            )

            enriched = {
                "date":        date_str,
                "type":        tx.get(
                    "Transaction Type", ""
                ),
                "description": tx.get("Description", ""),
                "debit":       debit  if debit  else None,
                "credit":      credit if credit else None,
                "is_new":      is_new,
                "date_flag":   date_flag,
            }

            all_transactions.append(enriched)
            if is_new:
                new_transactions.append(enriched)

        logger.info(
            f"Detection: {len(new_transactions)} new / "
            f"{len(all_transactions)} total"
        )
        return new_transactions, all_transactions

        # =========================================================================
        # SINGLE ACCOUNT COMPARISON - FIXED BALANCE LOGIC
        # =========================================================================
    def compare_account(self, account_number: str,
                        account_name: str) -> dict:
        """Compare today vs yesterday for one account.
        Uses cross-file balance comparison for accuracy.
        """
        today_file = self._find_csv(
            self._get_folder(self.today),
            account_number
        )
        yesterday_file = self._find_csv(
            self._get_folder(self.yesterday),
            account_number
        )

        # ── No file today ─────────────────────────────────────────────
        if not today_file:
            return self._build_result(
                account_number=account_number,
                account_name=account_name,
                status="no_file",
                message="No file downloaded today",
            )

        # ── Parse today's file ────────────────────────────────────────
        today_data = self._parse_bmo_csv(today_file)
        if today_data["error"]:
            return self._build_result(
                account_number=account_number,
                account_name=account_name,
                status="error",
                message=(
                    f"Parse error: {today_data['error']}"
                ),
            )

        # ── Extract TODAY's balances ───────────────────────────────────
        today_balances = self._extract_balances(
            today_data["metadata"]
        )
        curr_bal = today_balances["current_ledger"]

        # ── Extract YESTERDAY's balance for true comparison ───────────
        prev_bal = None
        bal_changed = False

        if yesterday_file:
            yesterday_data = self._parse_bmo_csv(
                yesterday_file
            )
            yesterday_balances = self._extract_balances(
                yesterday_data["metadata"]
            )
            # Use YESTERDAY's current ledger as our baseline
            prev_bal = yesterday_balances["current_ledger"]
            bal_changed = curr_bal != prev_bal

            logger.info(
                f"{account_number} Balance: "
                f"Yesterday={prev_bal:,.2f} "
                f"Today={curr_bal:,.2f} "
                f"Changed={bal_changed}"
            )
        else:
            # No yesterday file - use BMO's own previous field
            prev_bal = today_balances["previous_ledger"]
            bal_changed = curr_bal != prev_bal
            logger.info(
                f"{account_number} No yesterday file - "
                f"using BMO previous field: {prev_bal:,.2f}"
            )

        # ── Build cross-day balance info for email ────────────────────
        balances = {
            "current_ledger": curr_bal,
            "previous_ledger": prev_bal if prev_bal
                                           is not None
            else today_balances[
                "previous_ledger"
            ],
            "current_available": today_balances[
                "current_available"
            ],
            "previous_available": today_balances[
                "previous_available"
            ],
            "currency": today_balances["currency"],
            "source": "cross_file" if yesterday_file
            else "bmo_field",
        }

        # ── Build yesterday's transaction keys ────────────────────────
        yesterday_keys = set()
        if yesterday_file:
            for tx in yesterday_data["transactions"]:
                yesterday_keys.add(self._make_tx_key(tx))
            logger.debug(
                f"Yesterday keys: {len(yesterday_keys)}"
            )
        else:
            logger.info(
                f"No yesterday file for {account_number}"
            )

        # ── Detect new transactions ───────────────────────────────────
        new_transactions, all_transactions = \
            self._find_new_transactions(
                today_data["transactions"],
                yesterday_keys
            )

        # ── Detect offsetting ─────────────────────────────────────────
        new_debits = sum(
            t["debit"] for t in new_transactions
            if t["debit"]
        )
        new_credits = sum(
            t["credit"] for t in new_transactions
            if t["credit"]
        )
        is_offsetting = (
                len(new_transactions) >= 2
                and abs(new_debits - new_credits) < 0.01
                and new_debits > 0
        )

        # ── Determine status ──────────────────────────────────────────
        if new_transactions:
            if is_offsetting and not bal_changed:
                status = "offsetting"
                message = (
                    f"{len(new_transactions)} transactions "
                    f"(offsetting — balance unchanged)"
                )
            else:
                status = "new_activity"
                message = (
                    f"{len(new_transactions)} "
                    f"new transaction(s)"
                )
        else:
            status = "no_activity"
            message = "No new transactions today"

        logger.info(
            f"{account_number}: {status} — {message}"
        )

        return self._build_result(
            account_number=account_number,
            account_name=account_name,
            status=status,
            message=message,
            new_transactions=new_transactions,
            all_transactions=all_transactions,
            balances=balances,
            bal_changed=bal_changed,
            is_offsetting=is_offsetting,
            today_file=today_file,
            new_debits=new_debits,
            new_credits=new_credits,
        )

    # =========================================================================
    # RESULT BUILDER
    # =========================================================================
    def _build_result(self,
                      account_number:   str,
                      account_name:     str,
                      status:           str,
                      message:          str,
                      new_transactions: list  = None,
                      all_transactions: list  = None,
                      balances:         dict  = None,
                      bal_changed:      bool  = False,
                      is_offsetting:    bool  = False,
                      today_file:       str   = None,
                      new_debits:       float = 0.0,
                      new_credits:      float = 0.0,
                      ) -> dict:
        return {
            "account_number":   account_number,
            "account_name":     account_name,
            "status":           status,
            "message":          message,
            "new_transactions": new_transactions or [],
            "all_transactions": all_transactions or [],
            "balances":         balances or {},
            "bal_changed":      bal_changed,
            "is_offsetting":    is_offsetting,
            "file_path":        today_file or "",
            "new_debits":       new_debits,
            "new_credits":      new_credits,
        }

    # =========================================================================
    # COMPARE ALL ACCOUNTS
    # =========================================================================
    def compare_all(self, accounts: list) -> dict:
        """
        Run comparison for all accounts.
        Single pass - no double processing.
        """
        results          = []
        new_count        = 0
        no_activity      = 0
        offsetting_count = 0
        total_new_tx     = 0

        for acc in accounts:
            result = self.compare_account(
                acc["account_number"],
                acc["account_name"]
            )
            results.append(result)

            if result["status"] == "new_activity":
                new_count    += 1
                total_new_tx += len(
                    result["new_transactions"]
                )
            elif result["status"] == "offsetting":
                offsetting_count += 1
                total_new_tx     += len(
                    result["new_transactions"]
                )
            else:
                no_activity += 1

        summary = {
            "run_date":          self.today,
            "run_time":          datetime.now().strftime(
                                     "%I:%M %p"
                                 ),
            "total_accounts":    len(accounts),
            "accounts_with_new": new_count,
            "offsetting":        offsetting_count,
            "no_activity":       no_activity,
            "total_new_tx":      total_new_tx,
            "output_folder":     self._get_folder(
                                     self.today
                                 ),
            "results":           results,
        }

        logger.info(
            f"Summary: {new_count} new activity / "
            f"{offsetting_count} offsetting / "
            f"{no_activity} no activity / "
            f"{total_new_tx} total new transactions"
        )

        return summary
