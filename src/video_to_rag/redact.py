"""Credential masking for every message that leaves the tool (pure)."""

import logging
import re
from collections.abc import Iterable

# scheme://<userinfo>@ — userinfo stops at whitespace or the start of path/query/fragment;
# greedy, so a password with a raw "@" is masked up to the last "@" before the host.
USERINFO_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)[^\s/?#]+@")


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """Mask the user and password of every URL: `scheme://user:pass@host` -> `scheme://***@host`.

    `secrets` (known credentials, e.g. the configured proxy's) are also masked wherever they
    appear, URL or not.
    """
    text = USERINFO_RE.sub(r"\1***@", text)
    for secret in sorted(set(secrets), key=len, reverse=True):
        text = text.replace(secret, "***")
    return text


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
