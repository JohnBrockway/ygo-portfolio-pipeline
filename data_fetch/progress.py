"""A throttled progress reporter, so long loops show they're alive without a log line per item."""
import time


class Progress:
    """Logs at most one INFO line every `every_seconds`, however often update() is called.

    Call update() once per item or request; it costs next to nothing when no line is due.
    Messages take logging's %-style arguments, so nothing is formatted unless a line is emitted.
    """

    def __init__(self, logger, every_seconds=30.0):
        self._logger = logger
        self._every_seconds = every_seconds
        self._last_logged = time.monotonic()

    def update(self, message, *args):
        now = time.monotonic()
        if now - self._last_logged >= self._every_seconds:
            self._last_logged = now
            self._logger.info(message, *args)