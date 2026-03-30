"""Centralised structured logger for RazDashboard.

Usage:
    from src.logger import get_logger
    _log = get_logger(__name__)
    _log.info("Fetching data", extra={"ticker": "AMD"})
    _log.error("Fetch failed", exc_info=True, extra={"ticker": "AMD"})
"""
import logging
import sys
from datetime import datetime


class _ContextFormatter(logging.Formatter):
    """Formats: TIMESTAMP LEVEL module:lineno — message [key=val ...]"""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        level = record.levelname[:4]
        location = f"{record.module}:{record.lineno}"
        msg = record.getMessage()

        _skip = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
            "taskName",
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in _skip}
        suffix = "  " + "  ".join(f"{k}={v}" for k, v in extras.items()) if extras else ""

        line = f"{ts} {level} {location} — {msg}{suffix}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def _build_handler() -> logging.StreamHandler:
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(_ContextFormatter())
    return h


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger, initialised once."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(_build_handler())
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
    return logger
