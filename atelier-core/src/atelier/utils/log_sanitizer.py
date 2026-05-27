"""Log sanitizer - strips control characters for CWE-117 log-injection prevention.

Replaces characters outside the printable ASCII range (0x20-0x7E) plus
standard whitespace (\\n, \\t, \\r) with a unicode replacement character.
This prevents attacker-controlled strings from injecting newlines or escape
sequences into structured log output.

The implementation is intentionally minimal - a single regex substitution
with no external dependencies.
"""

from __future__ import annotations

import re

# Matches any character that is NOT:
#   - printable ASCII (0x20-0x7E)
#   - newline, carriage return, or tab
_CONTROL_CHAR_RE = re.compile(r"[^\x20-\x7E\n\r\t]")
_REPLACEMENT = "\ufffd"  # Unicode replacement character


def sanitize(value: str) -> str:
    """Strip control characters from *value* for safe log output.

    Args:
        value: The string to sanitize.

    Returns:
        A copy of *value* with non-printable characters replaced by U+FFFD.
    """
    return _CONTROL_CHAR_RE.sub(_REPLACEMENT, value)
