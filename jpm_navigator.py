# jpm_navigator.py
# ── JPM Playwright Navigation & Download Logic ────────────────────────────────

import os
import re
import shutil
import threading
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from config import DEFAULT_OUTPUT_FOLDER

# ── Constants ─────────────────────────────────────────────────────────────────
JPM_LOGIN_URL = (
    "https://access.jpmorgan.bank.in/sso/redirectlogin"
    "?brand=jpma&URI=https://accessportal.jpmorgan.com"
)

WAIT_TIMEOUT  = 60_000   # ms
FUND_NAME     = "JPM"    # Used in output filename


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_report_date() -> datetime:
    """Returns previous business day."""
    today  = datetime.today()
    offset = 1
    if today.weekday() == 0:   # Monday → Friday
        offset = 3
    elif today.weekday() == 6: # Sunday → Friday
        offset = 2
    return today - timedelta(days=offset)


def get_output_folder() -> str:
    """Saves to JPM_Reports/ under the shared SharePoint output root
    (same root BMO writes to — see DEFAULT_OUTPUT_FOLDER in config.py)."""
    folder = os.path.join(DEFAULT_OUTPUT_FOLDER, "JPM_Reports")
    os.makedirs(folder, exist_ok=True)
    return folder


def get_output_filename(report_date: datetime) -> str:
    """Returns filename: JPM_YYYY-MM-DD.csv"""
    return f"{FUND_NAME}_{report_date.strftime('%Y-%m-%d')}.csv"


# ── Step 1 — Login ────────────────────────────────────────────────────────────
def login(page, username: str, password: str, log):
    log("🌐 Navigating to JPM login page...")
    page.goto(JPM_LOGIN_URL, wait_until="networkidle")

    log("👤 Entering username...")
    page.get_by_label("Username").fill(username)
    page.get_by_role(
        "button", name=re.compile("continue", re.IGNORECASE)
    ).click()

    log("🔑 Entering password...")
    pwd_field = page.locator("#password-input")
    pwd_field.wait_for(state="visible", timeout=WAIT_TIMEOUT)
    pwd_field.fill(password)
    page.get_by_role(
        "button", name=re.compile("log in|sign in|submit", re.IGNORECASE)
    ).click()

    log("⏸  Waiting for OTP to be entered by user...")


# ── Step 2 — Wait for OTP confirmation from GUI ───────────────────────────────
def wait_for_otp(otp_event: threading.Event, log):
    """Blocks until GUI signals OTP has been entered."""
    log("🔐 Browser is on OTP screen — please enter your RSA token.")
    otp_event.wait()
    log("✅ OTP confirmed — continuing...")


# ── Step 3 — Wait for dashboard after OTP ────────────────────────────────────
def wait_for_dashboard(page, log):
    log("⏳ Waiting for JPM dashboard...")
    page.wait_for_selector("text=Welcome to Access", timeout=WAIT_TIMEOUT)
    log("✅ Logged in successfully!")


# ── Step 4 — Navigate to Transaction Summary tab ─────────────────────────────
def navigate_to_transactions(page, log):
    log("📂 Clicking View Transactions...")
    page.get_by_role(
        "button", name=re.compile("View Transactions", re.IGNORECASE)
    ).click()

    # Wait for the Account Balances tab to confirm the accounts page has loaded —
    # replaces bare wait_for_timeout(3_000)
    log("⏳ Waiting for accounts page to load...")
    try:
        page.get_by_role(
            "tab", name=re.compile("Account Balances", re.IGNORECASE)
        ).wait_for(state="visible", timeout=WAIT_TIMEOUT)
        log("✅ Accounts page loaded.")
    except PlaywrightTimeout:
        log("⚠️  Accounts page did not load in time.")
        raise

    # Now safe to click Transaction Summary tab
    log("📑 Clicking Transaction Summary tab...")
    page.get_by_role(
        "tab", name=re.compile("Transaction Summary", re.IGNORECASE)
    ).click()

    # Wait for the date filter option to confirm the tab content has rendered —
    # replaces bare wait_for_timeout(3_000)
    log("⏳ Waiting for Transaction Summary tab to render...")
    try:
        page.get_by_role(
            "option", name=re.compile("Prior day", re.IGNORECASE)
        ).wait_for(state="visible", timeout=WAIT_TIMEOUT)
        log("✅ Transaction Summary tab loaded.")
    except PlaywrightTimeout:
        log("⚠️  Transaction Summary tab did not render in time.")
        raise


# ── Step 5 — Select Prior Business Day ───────────────────────────────────────
def select_prior_day(page, report_date: datetime, log):
    log(f"📅 Selecting date: {report_date.strftime('%A, %B %d %Y')}...")

    if report_date.weekday() == 4:  # Friday — must use calendar picker
        # "Prior day" dropdown only goes back 1 day — on Monday that gives
        # Friday, but if the portal is opened on a day where prior day
        # dropdown doesn't cover Friday we use the calendar instead.
        log("📅 Report date is Friday — using Salt UI calendar picker...")
        _select_date_via_calendar(page, report_date, log)

    else:
        log("📅 Clicking Prior day dropdown option...")
        page.get_by_role(
            "option", name=re.compile("Prior day", re.IGNORECASE)
        ).click()

    # Wait for the balance summary panel to confirm the page has reloaded
    # with the selected date — "Total Net Impact" is always rendered
    log("⏳ Waiting for balance summary to load...")
    try:
        page.wait_for_selector("text=Total Net Impact", timeout=WAIT_TIMEOUT)
        log("✅ Balance summary loaded.")
    except PlaywrightTimeout:
        log("⚠️  Balance summary did not appear — page may not have loaded.")
        raise


def _select_date_via_calendar(page, report_date: datetime, log):
    """
    Selects a specific date using the Salt UI calendar widget.
    Salt UI does NOT render <input type='date'> — it renders a custom
    calendar grid. We click the day cell directly.
    """
    # Open the calendar
    log("📅 Opening calendar picker...")
    try:
        page.get_by_role(
            "button", name=re.compile("Select date|calendar|date", re.IGNORECASE)
        ).first.click()
    except PlaywrightTimeout:
        log("⚠️  Calendar button not found.")
        raise

    # Wait for the calendar grid to appear
    log("⏳ Waiting for calendar to open...")
    try:
        page.wait_for_selector("[role='grid']", timeout=WAIT_TIMEOUT)
        log("✅ Calendar opened.")
    except PlaywrightTimeout:
        log("⚠️  Calendar grid did not appear.")
        raise

    # Navigate to the correct month if needed
    target_month = report_date.strftime("%B %Y")   # e.g. "July 2025"
    _navigate_calendar_to_month(page, target_month, log)

    # Click the day cell — Salt UI renders each day as role="gridcell"
    # with the day number as its text content
    day_str = str(report_date.day)   # "4", "18" etc — no leading zero
    log(f"📅 Clicking day {day_str}...")

    # Filter to exact day number to avoid e.g. clicking "14" when we want "4"
    day_cell = page.locator("[role='gridcell']").filter(
        has_text=re.compile(rf"^{day_str}$")
    ).first

    try:
        day_cell.wait_for(state="visible", timeout=WAIT_TIMEOUT)
        day_cell.click()
        log(f"✅ Date {report_date.strftime('%Y-%m-%d')} selected.")
    except PlaywrightTimeout:
        log(f"⚠️  Day cell '{day_str}' not found in calendar.")
        raise


def _navigate_calendar_to_month(page, target_month: str, log):
    """
    Clicks the calendar's Next/Previous month buttons until the calendar
    header shows the target month (e.g. 'July 2025').
    Gives up after 24 attempts to avoid infinite loops.
    """
    log(f"📅 Navigating calendar to {target_month}...")

    for attempt in range(24):
        # Read current month label from the calendar header
        # Salt UI typically renders it as a button or heading inside the grid
        header = page.locator(
            "[role='grid'] button, [role='grid'] [role='heading'], "
            "[data-testid='calendar-month-year'], .saltCalendar-header"
        ).first

        try:
            header.wait_for(state="visible", timeout=5_000)
            current = header.inner_text().strip()
        except PlaywrightTimeout:
            log("⚠️  Could not read calendar header — proceeding anyway.")
            break

        if target_month.lower() in current.lower():
            log(f"✅ Calendar is on correct month: {current}")
            break

        # Decide direction — parse year+month to compare
        try:
            current_dt = datetime.strptime(current, "%B %Y")
            target_dt  = datetime.strptime(target_month, "%B %Y")
        except ValueError:
            log(f"⚠️  Could not parse calendar header '{current}' — proceeding.")
            break

        if target_dt < current_dt:
            log(f"⬅️  Clicking previous month (on {current})...")
            page.get_by_role(
                "button", name=re.compile("previous|prev|back|<", re.IGNORECASE)
            ).first.click()
        else:
            log(f"➡️  Clicking next month (on {current})...")
            page.get_by_role(
                "button", name=re.compile("next|forward|>", re.IGNORECASE)
            ).first.click()

        page.wait_for_timeout(400)  # small pause for calendar animation

    else:
        log("⚠️  Could not navigate to target month after 24 attempts.")


# ── Step 5b — Check balance figures ──────────────────────────────────────────
# FIX #2 — this was defined but never called. Now wired into run_jpm.
# FIX #3 — old JS used nextElementSibling which breaks in Salt UI nesting.
#           Replaced with ancestor-walk strategy that is DOM-structure-agnostic.
def has_activity(page, log) -> bool:
    """
    Reads the '1 Day' and '2+ Days' net impact figures from the balance
    summary panel.

    Strategy: find the label element, walk UP the DOM to its nearest
    ancestor that also contains a numeric value as a descendant, then
    return that value. Survives any Salt UI nesting depth.
    """
    log("🔢 Reading 1 Day / 2+ Days balance figures...")

    try:
        result = page.evaluate("""
            () => {
                /**
                 * Given a label string, find its DOM element, walk up until
                 * we reach an ancestor that contains a child with a numeric
                 * value, and return that value as a string.
                 * Returns '0.00' if nothing found.
                 */
                function getAmountForLabel(labelText) {
                    const allEls = Array.from(document.querySelectorAll('*'));
                    const labelEl = allEls.find(
                        el => el.children.length === 0 &&
                              el.innerText?.trim() === labelText
                    );

                    if (!labelEl) return '0.00';

                    // Only accept strings that look like a number —
                    // optional leading minus, digits, optional commas, optional decimal
                    const numericPattern = /^-?[\d,]+(\.\d+)?$/;

                    let ancestor = labelEl.parentElement;
                    while (ancestor && ancestor !== document.body) {
                        const candidates = Array.from(
                            ancestor.querySelectorAll('*')
                        );
                        for (const c of candidates) {
                            if (c === labelEl) continue;          // skip the label itself
                            if (c.children.length > 0) continue;  // leaf nodes only
                            const t = c.innerText?.trim() ?? '';
                            if (numericPattern.test(t)) {
                                return t;
                            }
                        }
                        ancestor = ancestor.parentElement;
                    }
                    return '0.00';
                }

                return {
                    oneDay : getAmountForLabel('1 Day'),
                    twoDay : getAmountForLabel('2+ Days'),
                };
            }
        """)

        one_day_str = result.get("oneDay", "0.00")
        two_day_str = result.get("twoDay", "0.00")
        log(f"📊 1 Day: {one_day_str}  |  2+ Days: {two_day_str}")

        def to_float(val: str) -> float:
            cleaned = re.sub(r"[^\d.\-]", "", val)
            return float(cleaned) if cleaned else 0.0

        one_day_amt = abs(to_float(one_day_str))
        two_day_amt = abs(to_float(two_day_str))

        if one_day_amt == 0.0 and two_day_amt == 0.0:
            log("📭 1 Day and 2+ Days are both 0.00 — no transactions to export.")
            return False

        log("✅ Activity detected — proceeding to select transactions.")
        return True

    except Exception as e:
        log(f"⚠️  Could not read balance figures ({e}) — falling back to optimistic.")
        return True  # optimistic fallback — let Step 6 decide


# ── Step 6 — Select all transactions ─────────────────────────────────────────
# FIX #2 — removed tbody tr row count check (gave false positive from
#           Account Balances tab). has_activity() already confirmed rows exist
#           before this function is called.
def select_all_transactions(page, log) -> bool:
    """
    Ticks the select-all checkbox in the Transaction Summary table header.
    Only called AFTER has_activity() confirms there are rows to select.
    """
    log("☑️  Selecting all transactions...")

    header_checkbox = page.locator("thead input.saltCheckbox-input").nth(0)

    try:
        header_checkbox.scroll_into_view_if_needed()
        header_checkbox.wait_for(state="visible", timeout=WAIT_TIMEOUT)
    except PlaywrightTimeout:
        log("⚠️  Select-all checkbox not found in thead.")
        return False

    if not header_checkbox.is_checked():
        header_checkbox.click(force=True)

    # Confirm the checkbox actually registered as checked
    try:
        page.wait_for_function(
            """() => {
                const cb = document.querySelector('thead input.saltCheckbox-input');
                return cb && cb.checked;
            }""",
            timeout=10_000,
        )
        log("✅ All transactions selected.")
    except PlaywrightTimeout:
        log("⚠️  Checkbox did not confirm as checked — proceeding anyway.")

    return True


# ── Steps 7+8 — Export CSV and save file (atomic) ────────────────────────────
# FIX #4 — old code split export click and download into two separate functions
#           with a polling loop. Replaced with expect_download() which wraps
#           the click — no race condition, no polling, no corrupt file risk.
def export_and_save(page, report_date: datetime, log) -> str:
    """
    Opens the Transaction Details dropdown, clicks Export to CSV,
    and captures the download via Playwright's expect_download().
    Returns the full path of the saved file, or None on failure.
    """
    log("💾 Clicking Transaction Details dropdown...")

    txn_btn = page.locator(
        "button.saltButton.menuButton"
    ).filter(has_text=re.compile(r"Transaction details", re.IGNORECASE)).first

    try:
        txn_btn.wait_for(state="visible", timeout=WAIT_TIMEOUT)
    except PlaywrightTimeout:
        log("⚠️  Transaction Details button not found.")
        return None

    if not txn_btn.is_enabled():
        log("⚠️  Transaction Details button is disabled — nothing to export.")
        return None

    txn_btn.click()
    log("🔽 Dropdown opened.")

    page.wait_for_selector("[role='menu']", timeout=5_000)

    csv_item = page.locator("[role='menuitem']").filter(
        has_text=re.compile(r"csv", re.IGNORECASE)
    ).first
    csv_item.wait_for(state="visible", timeout=5_000)

    output_folder   = get_output_folder()
    output_filename = get_output_filename(report_date)
    dest            = os.path.join(output_folder, output_filename)

    log("📄 Selecting Export to CSV — waiting for download...")

    # Listener is registered BEFORE the click — nothing can be missed
    with page.expect_download(timeout=60_000) as download_info:
        csv_item.click()

    download = download_info.value

    failure = download.failure()
    if failure:
        log(f"❌ Download failed: {failure}")
        return None

    download.save_as(dest)
    log(f"✅ CSV export complete.")
    log(f"📁 File saved → {dest}")
    return dest


# ── Main Runner ───────────────────────────────────────────────────────────────
def run_jpm(username: str, password: str,
            otp_event: threading.Event,
            log_callback,
            stop_flag: threading.Event):

    def log(msg):
        log_callback(msg)

    report_date   = get_report_date()
    output_folder = get_output_folder()
    download_temp = os.path.join(output_folder, "_temp")
    os.makedirs(download_temp, exist_ok=True)

    log("=" * 50)
    log("   JPM Transaction Extractor")
    log("=" * 50)
    log(f"📅 Report date: {report_date.strftime('%A, %B %d %Y')}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            channel        = "msedge",
            headless       = False,
            downloads_path = download_temp,
        )
        context = browser.new_context(accept_downloads=True)
        page    = context.new_page()

        try:
            if stop_flag.is_set():
                log("⏹ Stopped.")
                return None

            # Step 1 — Login
            login(page, username, password, log)

            if stop_flag.is_set():
                log("⏹ Stopped.")
                return None

            # Step 2 — Wait for user to enter OTP in browser
            wait_for_otp(otp_event, log)

            if stop_flag.is_set():
                log("⏹ Stopped.")
                return None

            # Step 3 — Wait for dashboard
            wait_for_dashboard(page, log)

            if stop_flag.is_set():
                log("⏹ Stopped.")
                return None

            # Step 4 — Navigate to transactions
            navigate_to_transactions(page, log)

            if stop_flag.is_set():
                log("⏹ Stopped.")
                return None

            # Step 5 — Select prior day
            select_prior_day(page, report_date, log)

            if stop_flag.is_set():
                log("⏹ Stopped.")
                return None

            # Step 5b — Check balance figures before touching the table
            # FIX #2 — has_activity was defined but never called before this fix
            if not has_activity(page, log):
                log("📭 No transactions for this date — exiting cleanly.")
                return None

            if stop_flag.is_set():
                log("⏹ Stopped.")
                return None

            # Step 6 — Select all transactions
            if not select_all_transactions(page, log):
                log("📭 Could not select transactions — exiting.")
                return None

            if stop_flag.is_set():
                log("⏹ Stopped.")
                return None

            # Steps 7+8 — Export CSV and save file (atomic)
            dest = export_and_save(page, report_date, log)
            if not dest:
                return None

            log("=" * 50)
            log("✅ JPM extraction complete!")
            log(f"📄 Saved → {dest}")
            log("=" * 50)
            return dest

        except Exception as e:
            log(f"❌ Unexpected error: {e}")
            raise

        finally:
            browser.close()
