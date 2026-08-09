# =============================================================================
# BRIDGE BMO DOWNLOADER - ENTRY POINT
# =============================================================================

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Initialize logging before anything else ───────────────────
from core.logger_setup import setup_logging
setup_logging()

import logging
logger = logging.getLogger("BridgeBMO.Main")
logger.info("Bridge BMO Downloader starting...")

from gui.app import main

if __name__ == "__main__":
    main()
