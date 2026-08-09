# =============================================================================
# RSA TOKEN / MFA HANDLER - Thread Safe
# =============================================================================

import threading
import logging

logger = logging.getLogger("BridgeBMO.MFA")


class MFAHandler:
    """
    Thread-safe MFA pause handler.
    Background thread waits here.
    Main thread calls resume() when user confirms.
    """

    def __init__(self):
        self._resume_event = threading.Event()

    def get_resume_event(self) -> threading.Event:
        return self._resume_event

    def wait_for_mfa(self):
        """Called from background thread - blocks until resumed."""
        logger.info("Waiting for MFA completion...")
        self._resume_event.clear()
        self._resume_event.wait()
        logger.info("MFA confirmed - resuming ✅")

    def resume(self):
        """Called from main thread when user confirms MFA."""
        self._resume_event.set()
