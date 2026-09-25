from __future__ import annotations

import logging
import sys

from .security import redact_secrets

_CONFIGURED = False

SENSITIVE_LOG_KEYS = ("token", "authorization", "secret", "password", "api_key", "client_secret")


class RedactionFilter(logging.Filter):
    """Scrubs obvious secrets from every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact_secrets(record.msg, aggressive=True)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        k: redact_secrets(str(v), aggressive=True) if isinstance(v, str) else v
                        for k, v in record.args.items()
                    }
                else:
                    record.args = tuple(
                        redact_secrets(a, aggressive=True) if isinstance(a, str) else a
                        for a in record.args
                    )
        except Exception:  # pragma: no cover - logging must never raise
            return True
        return True


def configure_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.addFilter(RedactionFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(f, RedactionFilter) for f in logger.filters):
        logger.addFilter(RedactionFilter())
    return logger
