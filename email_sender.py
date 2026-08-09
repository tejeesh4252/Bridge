# =============================================================================
# EMAIL SENDER - Updated with Weekly Report method
# =============================================================================

import logging
from datetime import datetime

logger = logging.getLogger("BridgeBMO.EmailSender")


class EmailSender:
    """
    Sends HTML emails via Outlook desktop.
    Handles: daily summary, weekly report, error alerts.
    """

    def __init__(self, recipients: list):
        self.recipients = recipients

    # =========================================================================
    # SEND DAILY SUMMARY (existing - unchanged)
    # =========================================================================
    def send_summary(self, summary: dict) -> tuple:
        """Send daily transaction summary email."""
        try:
            import win32com.client
            outlook = win32com.client.Dispatch(
                "Outlook.Application"
            )
            mail = outlook.CreateItem(0)
            mail.To = "; ".join(self.recipients)

            date_str  = datetime.strptime(
                summary["run_date"], "%Y-%m-%d"
            ).strftime("%B %d, %Y")
            new_count = summary["accounts_with_new"]
            off_count = summary["offsetting"]
            active    = new_count + off_count

            tag = (
                f"🟢 {active} Account(s) With Activity"
                if active > 0
                else "⚪ No New Activity"
            )
            mail.Subject = (
                f"BMO Daily Update  |  "
                f"{date_str}  |  {tag}"
            )
            mail.HTMLBody = self._build_daily_html(summary)
            mail.Send()

            logger.info(
                f"Daily email sent to "
                f"{len(self.recipients)} recipients"
            )
            return True, "✅ Daily email sent successfully"

        except ImportError:
            return False, (
                "❌ pywin32 not installed. "
                "Run: pip install pywin32"
            )
        except Exception as e:
            logger.error(f"Daily email error: {e}")
            return False, f"❌ Email failed: {str(e)}"

    # =========================================================================
    # SEND WEEKLY REPORT  ← NEW
    # =========================================================================
    def send_weekly_report(self, summary: dict) -> tuple:
        """
        Send Monday weekly transaction count report.
        summary: result from WeeklyReporter.generate_summary()
        """
        try:
            import win32com.client
            outlook = win32com.client.Dispatch(
                "Outlook.Application"
            )
            mail = outlook.CreateItem(0)

            # ── Recipients ────────────────────────────────────────────
            mail.To = "; ".join(self.recipients)

            # ── Subject ───────────────────────────────────────────────
            week_start = datetime.strptime(
                summary["week_start"], "%Y-%m-%d"
            ).strftime("%b %d")

            week_end = datetime.strptime(
                summary["week_end"], "%Y-%m-%d"
            ).strftime("%b %d, %Y")

            mail.Subject = (
                f"BMO Weekly Summary  |  "
                f"{week_start} – {week_end}  |  "
                f"📊 {summary['grand_total']} "
                f"Total Transactions"
            )

            # ── Body ──────────────────────────────────────────────────
            mail.HTMLBody = self._build_weekly_html(summary)
            mail.Send()

            logger.info(
                f"Weekly report sent to "
                f"{len(self.recipients)} recipients"
            )
            return True, "✅ Weekly report sent successfully"

        except Exception as e:
            logger.error(f"Weekly email error: {e}")
            return False, f"❌ Weekly email failed: {str(e)}"

    # =========================================================================
    # WEEKLY HTML BUILDER  ← NEW
    # =========================================================================
    def _build_weekly_html(self, summary: dict) -> str:
        """Build weekly report HTML email."""

        week_start = datetime.strptime(
            summary["week_start"], "%Y-%m-%d"
        ).strftime("%B %d, %Y")

        week_end = datetime.strptime(
            summary["week_end"], "%Y-%m-%d"
        ).strftime("%B %d, %Y")

        generated = datetime.strptime(
            summary["generated_on"], "%Y-%m-%d"
        ).strftime("%B %d, %Y")

        # ── Build account rows ────────────────────────────────────────
        account_rows = ""
        for i, acc in enumerate(summary["accounts"]):
            row_bg = "#ffffff" if i % 2 == 0 else "#f8fafc"
            count  = acc["transaction_count"]

            # Highlight accounts with activity
            count_color = (
                "#1a56a0" if count > 0 else "#9ca3af"
            )
            count_weight = (
                "bold" if count > 0 else "normal"
            )

            # Data coverage indicator
            days        = acc["days_with_data"]
            coverage    = f"{days}/7 days"
            cov_color   = (
                "#16a34a" if days >= 5
                else "#d97706" if days >= 3
                else "#dc2626"
            )

            account_rows += f"""
            <tr style="background:{row_bg};">
              <td style="padding:9px 16px;
                          font-size:12px;
                          color:#374151;
                          border-bottom:
                          1px solid #f1f5f9;">
                {acc["account_name"]}
              </td>
              <td style="padding:9px 16px;
                          font-size:12px;
                          color:#6b7280;
                          text-align:center;
                          border-bottom:
                          1px solid #f1f5f9;">
                {acc["account_number"]}
              </td>
              <td style="padding:9px 16px;
                          font-size:13px;
                          font-weight:{count_weight};
                          color:{count_color};
                          text-align:center;
                          border-bottom:
                          1px solid #f1f5f9;">
                {count}
              </td>
              <td style="padding:9px 16px;
                          font-size:11px;
                          color:{cov_color};
                          text-align:center;
                          border-bottom:
                          1px solid #f1f5f9;">
                {coverage}
              </td>
            </tr>
            """

        # ── Data coverage note ────────────────────────────────────────
        folders_found = summary["folders_found"]
        if folders_found < 7:
            coverage_note = f"""
            <tr>
              <td colspan="4"
                  style="background:#fef9c3;
                         padding:8px 16px;
                         font-size:11px;
                         color:#854d0e;">
                ⚠️  Data available for {folders_found}
                out of 7 days in this week.
                {7 - folders_found} day(s) have no
                downloaded files.
              </td>
            </tr>
            """
        else:
            coverage_note = ""

        return f"""
        <html>
        <body style="margin:0; padding:20px;
                     background:#f1f5f9;
                     font-family:Segoe UI,
                     Arial,sans-serif;">

        <table width="680" cellpadding="0"
               cellspacing="0"
               style="margin:0 auto;
                      border-radius:10px;
                      overflow:hidden;
                      box-shadow:0 2px 8px
                      rgba(0,0,0,0.1);">

          <!-- ═══ HEADER ═══ -->
          <tr>
            <td style="background:#0f3460;
                       padding:22px 28px;">
              <div style="color:white;
                           font-size:18px;
                           font-weight:bold;">
                📊 &nbsp;
                BRIDGE BMO WEEKLY SUMMARY
              </div>
              <div style="color:#93c5fd;
                           font-size:12px;
                           margin-top:6px;">
                Week of {week_start}
                &nbsp;—&nbsp;
                {week_end}
              </div>
              <div style="color:#64748b;
                           font-size:11px;
                           margin-top:3px;">
                Generated: Monday, {generated}
              </div>
            </td>
          </tr>

          <!-- ═══ GRAND TOTAL BAR ═══ -->
          <tr>
            <td style="background:#1a56a0;
                       padding:14px 28px;">
              <table width="100%">
                <tr>
                  <td style="color:white;
                              font-size:15px;
                              font-weight:bold;">
                    📈 &nbsp;
                    Grand Total Transactions:
                    &nbsp;
                    <span style="font-size:22px;
                                  color:#bfdbfe;">
                      {summary["grand_total"]}
                    </span>
                  </td>
                  <td style="text-align:right;
                              color:#93c5fd;
                              font-size:12px;">
                    {summary["folders_found"]}/7
                    days with data
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- ═══ TABLE HEADER ═══ -->
          <tr>
            <td style="background:white;
                       padding:0;">
              <table width="100%"
                     cellpadding="0"
                     cellspacing="0">

                <tr style="background:#f8fafc;
                            border-bottom:
                            2px solid #e2e8f0;">
                  <th style="text-align:left;
                              padding:10px 16px;
                              font-size:11px;
                              color:#475569;
                              font-weight:bold;
                              width:45%;">
                    Account Name
                  </th>
                  <th style="text-align:center;
                              padding:10px 16px;
                              font-size:11px;
                              color:#475569;
                              font-weight:bold;
                              width:18%;">
                    Account No.
                  </th>
                  <th style="text-align:center;
                              padding:10px 16px;
                              font-size:11px;
                              color:#475569;
                              font-weight:bold;
                              width:18%;">
                    Transactions
                  </th>
                  <th style="text-align:center;
                              padding:10px 16px;
                              font-size:11px;
                              color:#475569;
                              font-weight:bold;
                              width:19%;">
                    Data Coverage
                  </th>
                </tr>

                <!-- Account rows -->
                {account_rows}

                <!-- Coverage warning if applicable -->
                {coverage_note}

                <!-- Grand Total row -->
                <tr style="background:#0f3460;">
                  <td style="padding:12px 16px;
                              font-size:13px;
                              font-weight:bold;
                              color:white;">
                    GRAND TOTAL
                  </td>
                  <td style="padding:12px 16px;
                              text-align:center;
                              color:#93c5fd;
                              font-size:12px;">
                    {len(summary["accounts"])} accounts
                  </td>
                  <td style="padding:12px 16px;
                              text-align:center;
                              font-size:20px;
                              font-weight:bold;
                              color:white;">
                    {summary["grand_total"]}
                  </td>
                  <td style="padding:12px 16px;
                              text-align:center;
                              color:#93c5fd;
                              font-size:12px;">
                    &nbsp;
                  </td>
                </tr>

              </table>
            </td>
          </tr>

          <!-- ═══ FOOTER ═══ -->
          <tr>
            <td style="background:#f8fafc;
                       padding:14px 28px;
                       border-top:
                       2px solid #e2e8f0;">
              <div style="color:#475569;
                           font-size:11px;">
                📁 &nbsp;
                <b>Source files:</b>
                <span style="color:#1a56a0;
                              font-family:Consolas;
                              font-size:10px;">
                  {summary.get(
                      "output_folder",
                      "BMO Downloads folder"
                  )}
                </span>
              </div>
              <div style="color:#94a3b8;
                           font-size:10px;
                           margin-top:4px;">
                Bridge BMO Downloader v2.0
                &nbsp;|&nbsp;
                AlterDomus Internal Tool
                &nbsp;|&nbsp;
                Weekly report sent every Monday
              </div>
            </td>
          </tr>

        </table>
        </body>
        </html>
        """

    # =========================================================================
    # DAILY HTML BUILDER (existing - unchanged)
    # =========================================================================
    def _build_daily_html(self, summary: dict) -> str:
        """Build complete daily HTML email body."""
        date_str = datetime.strptime(
            summary["run_date"], "%Y-%m-%d"
        ).strftime("%B %d, %Y")

        account_blocks = "".join(
            self._account_block(r)
            for r in summary["results"]
        )

        return f"""
        <html>
        <body style="margin:0; padding:20px;
                     background:#f1f5f9;
                     font-family:Segoe UI,
                     Arial,sans-serif;">
        <table width="680" cellpadding="0"
               cellspacing="0"
               style="margin:0 auto;
                      border-radius:10px;
                      overflow:hidden;
                      box-shadow:0 2px 8px
                      rgba(0,0,0,0.1);">
          <tr>
            <td style="background:#0f3460;
                       padding:20px 28px;">
              <div style="color:white;
                           font-size:18px;
                           font-weight:bold;">
                🏦 &nbsp;
                BRIDGE BMO DAILY UPDATE
              </div>
              <div style="color:#93c5fd;
                           font-size:12px;
                           margin-top:4px;">
                {date_str}
                &nbsp;|&nbsp;
                {summary["run_time"]}
              </div>
            </td>
          </tr>
          <tr>
            <td style="background:#1a56a0;
                       padding:10px 28px;">
              <span style="color:white;
                            font-size:12px;">
                📊 &nbsp;<b>Accounts:</b>
                {summary["total_accounts"]}
                &nbsp;|&nbsp;
                🟢 &nbsp;<b>New Activity:</b>
                {summary["accounts_with_new"]}
                &nbsp;|&nbsp;
                🟡 &nbsp;<b>Offsetting:</b>
                {summary["offsetting"]}
                &nbsp;|&nbsp;
                ⚪ &nbsp;<b>No Activity:</b>
                {summary["no_activity"]}
                &nbsp;|&nbsp;
                📝 &nbsp;<b>New Txns:</b>
                {summary["total_new_tx"]}
              </span>
            </td>
          </tr>
          <tr>
            <td style="background:white;
                       padding:20px 28px;">
              {account_blocks}
            </td>
          </tr>
          <tr>
            <td style="background:#f8fafc;
                       padding:14px 28px;
                       border-top:
                       2px solid #e2e8f0;">
              <div style="color:#475569;
                           font-size:12px;">
                📁 &nbsp;<b>Files saved to:</b>
                <span style="color:#1a56a0;
                              font-family:Consolas;
                              font-size:11px;">
                  &nbsp;{summary["output_folder"]}
                </span>
              </div>
              <div style="color:#94a3b8;
                           font-size:11px;
                           margin-top:4px;">
                Bridge BMO Downloader v2.0
                &nbsp;|&nbsp;
                AlterDomus Internal Tool
              </div>
            </td>
          </tr>
        </table>
        </body>
        </html>
        """

    # =========================================================================
    # ACCOUNT BLOCK (existing - unchanged)
    # =========================================================================
    def _account_block(self, result: dict) -> str:
        """Build HTML block for one account."""
        status   = result["status"]
        bal      = result.get("balances", {})
        curr     = bal.get("current_ledger",  0)
        prev     = bal.get("previous_ledger", 0)
        diff     = curr - prev
        has_new  = len(
            result.get("new_transactions", [])
        ) > 0

        if status == "new_activity":
            hdr_bg = "#dcfce7"
            hdr_fg = "#166534"
            icon   = "🟢"
            border = "#86efac"
        elif status == "offsetting":
            hdr_bg = "#fef9c3"
            hdr_fg = "#854d0e"
            icon   = "🟡"
            border = "#fde047"
        elif status in ("no_file", "error"):
            hdr_bg = "#fee2e2"
            hdr_fg = "#991b1b"
            icon   = "❌"
            border = "#fca5a5"
        else:
            hdr_bg = "#f1f5f9"
            hdr_fg = "#475569"
            icon   = "⚪"
            border = "#e2e8f0"

        if diff > 0:
            diff_str = (
                f"<span style='color:#16a34a;'>"
                f"+${diff:,.2f} ↑</span>"
            )
        elif diff < 0:
            diff_str = (
                f"<span style='color:#dc2626;'>"
                f"-${abs(diff):,.2f} ↓</span>"
            )
        else:
            if has_new:
                diff_str = (
                    "<span style='color:#d97706;"
                    "font-weight:bold;'>"
                    "⚠️ Balance unchanged — "
                    "transactions present</span>"
                )
            else:
                diff_str = (
                    "<span style='color:#6b7280;'>"
                    "No change — no activity</span>"
                )

        offset_warn = ""
        if result.get("is_offsetting"):
            offset_warn = """
            <tr>
              <td colspan="5"
                  style="background:#fef9c3;
                         padding:6px 12px;
                         font-size:11px;
                         color:#854d0e;">
                ⚠️ Offsetting transactions —
                balance unchanged but
                activity exists.
              </td>
            </tr>"""

        html = f"""
        <table width="100%" cellpadding="0"
               cellspacing="0"
               style="margin-bottom:10px;
                      border:1px solid {border};
                      border-radius:6px;
                      overflow:hidden;">
          <tr>
            <td style="background:{hdr_bg};
                       padding:10px 14px;">
              <table width="100%"><tr>
                <td style="color:{hdr_fg};
                            font-weight:bold;
                            font-size:13px;">
                  {icon} &nbsp;
                  {result["account_name"]}
                  <span style="font-weight:normal;
                                color:#64748b;
                                font-size:11px;">
                    &nbsp;
                    ({result["account_number"]})
                  </span>
                </td>
                <td style="text-align:right;
                            color:{hdr_fg};
                            font-size:12px;">
                  {result["message"]}
                </td>
              </tr></table>
            </td>
          </tr>
          <tr>
            <td style="background:#fafafa;
                       padding:5px 14px;
                       font-size:11px;
                       color:#475569;
                       border-bottom:
                       1px solid #e2e8f0;">
              💰 Previous: ${prev:,.2f}
              &nbsp;→&nbsp;
              Current: ${curr:,.2f}
              &nbsp;&nbsp;{diff_str}
            </td>
          </tr>
        """

        if result["new_transactions"]:
            html += f"""
          {offset_warn}
          <tr style="background:#f8fafc;">
            <th style="text-align:left;
                        padding:7px 14px;
                        font-size:11px;
                        color:#475569;
                        width:11%;">
              Date
            </th>
            <th style="text-align:left;
                        padding:7px 14px;
                        font-size:11px;
                        color:#475569;
                        width:20%;">
              Type
            </th>
            <th style="text-align:left;
                        padding:7px 14px;
                        font-size:11px;
                        color:#475569;
                        width:43%;">
              Description
            </th>
            <th style="text-align:right;
                        padding:7px 14px;
                        font-size:11px;
                        color:#475569;
                        width:13%;">
              Debit
            </th>
            <th style="text-align:right;
                        padding:7px 14px;
                        font-size:11px;
                        color:#475569;
                        width:13%;">
              Credit
            </th>
          </tr>
            """

            for i, tx in enumerate(
                result["new_transactions"]
            ):
                row_bg   = (
                    "#ffffff" if i % 2 == 0
                    else "#f8fafc"
                )
                debit_h  = (
                    f"<span style='color:#dc2626;'>"
                    f"${tx['debit']:,.2f}</span>"
                    if tx["debit"] else ""
                )
                credit_h = (
                    f"<span style='color:#16a34a;'>"
                    f"${tx['credit']:,.2f}</span>"
                    if tx["credit"] else ""
                )
                desc = tx["description"]
                if len(desc) > 55:
                    desc = desc[:52] + "..."

                html += f"""
          <tr style="background:{row_bg};
                      border-top:
                      1px solid #f1f5f9;">
            <td style="padding:6px 14px;
                        font-size:11px;">
              {tx["date"]}
            </td>
            <td style="padding:6px 14px;
                        font-size:11px;">
              {tx["type"]}
            </td>
            <td style="padding:6px 14px;
                        font-size:11px;">
              {desc}
            </td>
            <td style="padding:6px 14px;
                        font-size:11px;
                        text-align:right;">
              {debit_h}
            </td>
            <td style="padding:6px 14px;
                        font-size:11px;
                        text-align:right;">
              {credit_h}
            </td>
          </tr>
                """

        html += "</table>"
        return html

    # =========================================================================
    # ERROR EMAIL (existing - unchanged)
    # =========================================================================
    def send_error(self, error_msg: str) -> tuple:
        """Send error notification when script crashes."""
        try:
            import win32com.client
            outlook = win32com.client.Dispatch(
                "Outlook.Application"
            )
            mail         = outlook.CreateItem(0)
            mail.To      = "; ".join(self.recipients)
            mail.Subject = (
                f"❌ BMO Download FAILED  |  "
                f"{datetime.today().strftime('%B %d, %Y')}"
            )
            mail.HTMLBody = f"""
            <html>
            <body style="font-family:Segoe UI,
                         Arial,sans-serif;
                         padding:20px;
                         background:#f1f5f9;">
              <table width="600"
                     style="margin:0 auto;
                            border-radius:8px;
                            overflow:hidden;">
                <tr>
                  <td style="background:#dc2626;
                             padding:20px;">
                    <h2 style="color:white; margin:0;">
                      ❌  BMO Download Failed
                    </h2>
                    <p style="color:#fecaca;
                               font-size:12px;
                               margin:6px 0 0;">
                      {datetime.today().strftime(
                          '%B %d, %Y'
                      )}
                      &nbsp;|&nbsp;
                      {datetime.now().strftime('%I:%M %p')}
                    </p>
                  </td>
                </tr>
                <tr>
                  <td style="background:white;
                             padding:20px;
                             border:1px solid #e2e8f0;">
                    <p style="color:#374151;">
                      The automated BMO download
                      encountered an error.
                    </p>
                    <div style="background:#fef2f2;
                                border:1px solid #fecaca;
                                padding:12px;
                                border-radius:4px;
                                font-family:Consolas;
                                font-size:12px;
                                color:#991b1b;">
                      {error_msg}
                    </div>
                    <p style="color:#6b7280;
                               font-size:12px;
                               margin-top:16px;">
                      ⚠️ Please run manually today.
                    </p>
                  </td>
                </tr>
                <tr>
                  <td style="background:#f8fafc;
                             padding:10px 20px;
                             border:1px solid #e2e8f0;
                             border-top:none;">
                    <p style="color:#94a3b8;
                               font-size:11px;
                               margin:0;">
                      Bridge BMO Downloader v2.0
                    </p>
                  </td>
                </tr>
              </table>
            </body>
            </html>
            """
            mail.Send()
            logger.info("Error email sent")
            return True, "✅ Error email sent"

        except Exception as e:
            logger.error(f"Error email failed: {e}")
            return False, f"❌ Error email failed: {e}"
