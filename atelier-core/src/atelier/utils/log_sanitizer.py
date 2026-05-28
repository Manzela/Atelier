"""Log sanitizer - strips control characters for CWE-117 log-injection prevention.

Replaces characters outside the printable ASCII range (0x20-0x7E) with a
unicode replacement character. This prevents attacker-controlled strings
from injecting newlines, carriage returns, tabs, or escape sequences into
structured log output.

CWE-117 compliance: \\n, \\r, and \\t are explicitly NOT allowlisted because
they are the primary vectors for log injection attacks. Structured log fields
never legitimately contain raw newlines.

The implementation is intentionally minimal - a single regex substitution
with no external dependencies.
"""

from __future__ import annotations

import re

# Matches any character that is NOT printable ASCII (0x20-0x7E).
# CWE-117: newline, carriage return, and tab are intentionally excluded
# from the safe set — they are the primary log injection vectors.
_CONTROL_CHAR_RE = re.compile(r"[^\x20-\x7E]")
_REPLACEMENT = "\ufffd"  # Unicode replacement character


def sanitize(value: str) -> str:
    """Strip control characters from *value* for safe log output.

    All characters outside printable ASCII (0x20-0x7E) are replaced,
    including \\n, \\r, and \\t (CWE-117 log injection prevention).

    Args:
        value: The string to sanitize.

    Returns:
        A copy of *value* with non-printable characters replaced by U+FFFD.
    """
    return _CONTROL_CHAR_RE.sub(_REPLACEMENT, value)
