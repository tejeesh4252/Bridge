# =============================================================================
# BRIDGE BMO DOWNLOADER - SETTINGS CONFIGURATION
# =============================================================================
# Account data lives in BMO_Accounts.xlsx
# No credentials stored here - ever
# =============================================================================

import os

# =============================================================================
# EXCEL ACCOUNT FILE
# =============================================================================
ACCOUNTS_EXCEL_FILENAME = "BMO_Accounts.xlsx"
ACCOUNTS_SHEET_NAME     = "Accounts"
ACCOUNTS_COL_NAME       = "Account Name"
ACCOUNTS_COL_NUMBER     = "Account Number"
ACCOUNTS_COL_ACTIVE     = "Active"
ACCOUNTS_ACTIVE_VALUE   = "Yes"
ACCOUNTS_HEADER_ROW     = 4
ACCOUNTS_DATA_START     = 5

# =============================================================================
# BMO PORTAL SETTINGS
# =============================================================================
BMO_LOGIN_URL = (
    "https://www21.bmo.com/uiauth/AuthWeb/index.html"
    "?TAM_OP=login&ERROR_CODE=0x00000000"
    "&URL=%2F&HOSTNAME=www21.bmo.com"
    "&AUTHNLEVEL=4&PROTOCOL=https"
    "&v=265152026051222#/login/"
)

BMO_HOME_URL = (
    "https://www21.bmo.com/uiphpw/HPServicesWeb/"
    "#/homepage/dynamicHomepage"
)

# =============================================================================
# TIMEFRAME OPTIONS
# =============================================================================
TIMEFRAME_OPTIONS = [
    "Today",
    "Last 7 days",
    "Last 14 days",
    "Last 30 days",
    "Last 60 days",
    "Custom",
]
DEFAULT_TIMEFRAME = "Last 7 days"

# =============================================================================
# DEFAULT OUTPUT FOLDER
# =============================================================================
_onedrive = os.path.join(
    os.path.expanduser("~"),
    "OneDrive - AlterDomus",
    "RE SharePoint - Documents",
    "North America",
    "Cluster Files",
    "RE_Cluster 4",
    "Bridge Bank Statements Inventory"
)

DEFAULT_OUTPUT_FOLDER = r"C:\Users\wj596\OneDrive - AlterDomus\RA SharePoint - RE_Cluster 4\Bridge Bank Statements Inventory"


# =============================================================================
# DOWNLOAD SETTINGS
# =============================================================================
EXPORT_FORMAT        = "CSV"
DOWNLOAD_WAIT_SEC    = 15
PAGE_LOAD_WAIT_SEC   = 10
ACTION_DELAY_MS      = 800

# =============================================================================
# RETRY SETTINGS
# =============================================================================
MAX_RETRIES = 2

# =============================================================================
# FILE NAMING
# =============================================================================
FILE_PREFIX = "BMO"

# =============================================================================
# LOGGING
# =============================================================================
LOG_FILENAME = "download_log.json"
