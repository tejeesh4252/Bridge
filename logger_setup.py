# =============================================================================
# LOGGER SETUP
# Centralised logging for all modules
# =============================================================================

import logging
import os
from datetime import datetime


def setup_logging(output_base: str = None) -> logging.Logger:
    """
    Configure application-wide logging.
    Logs to console (INFO+) and daily log file (DEBUG+).
    """
    # ── Determine log folder ──────────────────────────────────────────────
    if output_base and os.path.exists(output_base):
        log_dir = os.path.join(output_base, "logs")
    else:
        log_dir = os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            ),
            "logs"
        )

    os.makedirs(log_dir, exist_ok=True)

    # ── Log filename ──────────────────────────────────────────────────────
    log_file = os.path.join(
        log_dir,
        f"bmo_{datetime.today().strftime('%Y%m%d')}.log"
    )

    # ── Root logger ───────────────────────────────────────────────────────
    logger = logging.getLogger("BridgeBMO")
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers on reload
    if logger.handlers:
        return logger

    # ── Formatter ─────────────────────────────────────────────────────────
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  "
        "%(name)-28s  %(message)s",
        datefmt="%H:%M:%S"
    )

    # ── Console handler (INFO+) ───────────────────────────────────────────
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # ── File handler (DEBUG+) ─────────────────────────────────────────────
    try:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception as e:
        logger.warning(f"Could not create log file: {e}")

    logger.info(f"Logging initialised → {log_file}")
    return logger
