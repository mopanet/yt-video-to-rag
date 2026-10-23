"""Credential masking for every message that leaves the tool (pure)."""

import logging
import re

# scheme://<userinfo>@ — userinfo stops at whitespace or the start of path/query/fragment;
# greedy, so a password with a raw "@" is masked up to the last "@" before the host.
USERINFO_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)[^\s/?#]+@")


def redact(text: str) -> str:
    """Mask the user and password of every URL: `scheme://user:pass@host` -> `scheme://***@host`."""
    return USERINFO_RE.sub(r"\1***@", text)


class RedactFilter(logging.Filter):
    """Logging filter that applies `redact` to the fully formatted message."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        return True


# The tool's one logger. Every module logs here directly: a logger's filters do not apply to
# records propagated from child loggers.
logger = logging.getLogger("video_to_rag")
logger.addFilter(RedactFilter())
