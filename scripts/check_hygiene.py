"""Repository hygiene gate — scans committed .md and .py files for anti-tells.

Detects pictographic emoji and AI-authorship/aspirational-stub strings that
violate the project style guide. See docs/STYLE.md for remediation guidance.

Usage:
    python scripts/check_hygiene.py          # scan git ls-files output
    python scripts/check_hygiene.py --help   # show this message

Exit codes:
    0  No violations found.
    1  One or more violations found (paths + reasons printed to stdout).
    2  Usage error.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

#: Pictographic emoji — U+1F000-U+1FAFF plus common standalone symbols.
#: Technical typography (arrows, math, dashes, bullets, section signs) is NOT in this range and is allowed.
EMOJI_RE = re.compile(r"[\U0001F000-\U0001FAFF✅❌⚠⭐✨\U0001F525️]")

#: Case-insensitive substrings that signal AI authorship or aspirational stubs.
DENYLIST: list[str] = [
    "co-authored-by: claude",
    "generated with claude",
    "\U0001f916",  # robot face U+1F916 (🤖) — stored as escape to avoid self-violation
    "vibe cod",
    "as an ai",
    "i'll help you",
    "current implementation",
    "replaces this with",
    "in a real implementation",
    "in a production implementation",
]

STYLE_GUIDE = "docs/STYLE.md"


# ---------------------------------------------------------------------------
# Core scan logic (importable for tests)
# ---------------------------------------------------------------------------


@dataclass
class Hit:
    """A single hygiene violation."""

    path: str
    line: int
    reason: str


def scan(paths: list[str]) -> list[Hit]:
    """Scan the given file paths and return all violations.

    Args:
        paths: Absolute or relative file paths to scan.

    Returns:
        List of :class:`Hit` instances; empty list means clean.
    """
    hits: list[Hit] = []
    for path in paths:
        try:
            content = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            # File disappeared between listing and scan — skip silently.
            continue

        lines = content.splitlines()
        lower_lines = [line.lower() for line in lines]

        for lineno, (line, lower_line) in enumerate(zip(lines, lower_lines, strict=True), start=1):
            # Emoji check
            for match in EMOJI_RE.finditer(line):
                hits.append(
                    Hit(
                        path=path,
                        line=lineno,
                        reason=f"pictographic emoji: {match.group()!r}",
                    )
                )

            # Denylist check
            for term in DENYLIST:
                if term in lower_line:
                    hits.append(
                        Hit(
                            path=path,
                            line=lineno,
                            reason=f"denylist match: {term!r}",
                        )
                    )

    return hits


# ---------------------------------------------------------------------------
# File discovery (git ls-files)
# ---------------------------------------------------------------------------


def _git_ls_files(root: Path) -> list[str]:
    """Return paths of all committed .md and .py files via git ls-files."""
    try:
        _git_cmd = ["git", "ls-files"]
        result = subprocess.run(  # noqa: S603
            _git_cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        sys.stderr.write(f"check_hygiene: could not run git ls-files: {exc}\n")
        sys.exit(2)

    files: list[str] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.endswith((".md", ".py")):
            files.append(str(root / stripped))
    return files


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Run the hygiene scan and return an exit code.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        0 if clean, 1 if violations found, 2 on usage error.
    """
    if argv is None:
        argv = sys.argv[1:]

    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    # Use cwd as the git repo root so the gate can be invoked from any repo.
    # This also makes the seeded-violation test work by cd-ing into a temp git repo.
    repo_root = Path.cwd()

    paths = _git_ls_files(repo_root)
    hits = scan(paths)

    if not hits:
        print("check_hygiene: no violations found.")
        return 0

    # Report violations
    for hit in hits:
        # Print path relative to repo root for readability
        try:
            rel = str(Path(hit.path).relative_to(repo_root))
        except ValueError:
            rel = hit.path
        print(f"{rel}:{hit.line}: {hit.reason}")

    print(
        f"\ncheck_hygiene: {len(hits)} violation(s) found."
        f" See {STYLE_GUIDE} for remediation guidance."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
