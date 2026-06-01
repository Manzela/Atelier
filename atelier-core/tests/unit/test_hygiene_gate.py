"""Tests for scripts/check_hygiene.py — the repo hygiene gate.

Two required directions per AT-099 acceptance:
    (a) Running the gate against the clean repo returns no hits (exit 0).
    (b) Running the gate against a seeded violation detects it (exit non-zero).

The scan logic is tested via the importable ``scan()`` function. The full
gate (git ls-files discovery) is tested via subprocess so the real entry
point is covered.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers — import the gate module without installing it
# ---------------------------------------------------------------------------

_GATE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "check_hygiene.py"


def _load_gate_module():  # type: ignore[return]
    """Dynamically load check_hygiene.py from the scripts/ directory."""
    spec = importlib.util.spec_from_file_location("check_hygiene", _GATE_PATH)
    assert spec is not None, f"Could not find gate at {_GATE_PATH}"
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Register in sys.modules before exec so @dataclass machinery can resolve the module.
    sys.modules["check_hygiene"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_gate = _load_gate_module()


# ---------------------------------------------------------------------------
# Unit tests — scan() function
# ---------------------------------------------------------------------------


class TestScanClean:
    """scan() returns no hits for clean content."""

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "clean.py"
        f.write_text("# nothing here\n", encoding="utf-8")
        assert _gate.scan([str(f)]) == []

    def test_technical_typography_not_flagged(self, tmp_path: Path) -> None:
        """Arrows, section signs, and math operators must not be flagged."""
        f = tmp_path / "clean.md"
        f.write_text(
            "# Section §1\n\nFlow: A → B → C\nThreshold ≥ 80%\nCross product: a \u00d7 b\n",
            encoding="utf-8",
        )
        assert _gate.scan([str(f)]) == []

    def test_checkmark_ascii_not_flagged(self, tmp_path: Path) -> None:
        f = tmp_path / "clean.md"
        f.write_text("- [x] Done\n- [ ] Pending\n", encoding="utf-8")
        assert _gate.scan([str(f)]) == []


class TestScanViolations:
    """scan() returns the expected hits for seeded violations."""

    def test_emoji_in_markdown(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.md"
        f.write_text("# Status\n\nAll good \U0001f7e2\n", encoding="utf-8")
        hits = _gate.scan([str(f)])
        assert len(hits) == 1
        assert "pictographic emoji" in hits[0].reason

    def test_checkmark_emoji_flagged(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.md"
        f.write_text("- ✅ Task complete\n", encoding="utf-8")  # U+2705 = ✅
        hits = _gate.scan([str(f)])
        assert any("pictographic emoji" in h.reason for h in hits)

    def test_denylist_co_authored_by_claude(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.md"
        f.write_text("Co-Authored-By: Claude Sonnet <noreply@anthropic.com>\n", encoding="utf-8")
        hits = _gate.scan([str(f)])
        assert any("co-authored-by: claude" in h.reason for h in hits)

    def test_denylist_generated_with_claude(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.md"
        f.write_text("Generated with Claude Code\n", encoding="utf-8")
        hits = _gate.scan([str(f)])
        assert any("generated with claude" in h.reason for h in hits)

    def test_denylist_vibe_cod(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("# vibe coding ftw\n", encoding="utf-8")
        hits = _gate.scan([str(f)])
        assert any("vibe cod" in h.reason for h in hits)

    def test_denylist_current_implementation(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text(
            "# current implementation will replace this with an LLM call\n", encoding="utf-8"
        )
        hits = _gate.scan([str(f)])
        assert any("current implementation" in h.reason for h in hits)

    def test_denylist_replaces_this_with(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("# replaces this with a real Playwright call\n", encoding="utf-8")
        hits = _gate.scan([str(f)])
        assert any("replaces this with" in h.reason for h in hits)

    def test_denylist_in_a_real_implementation(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("# in a real implementation we would call the API\n", encoding="utf-8")
        hits = _gate.scan([str(f)])
        assert any("in a real implementation" in h.reason for h in hits)

    def test_multiple_violations_reported(self, tmp_path: Path) -> None:
        f = tmp_path / "very_bad.md"
        f.write_text(
            "\U0001f680 Launch!\nGenerated with Claude\ncurrent implementation stub\n",
            encoding="utf-8",
        )
        hits = _gate.scan([str(f)])
        assert len(hits) >= 2

    def test_line_number_correct(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.md"
        f.write_text("line one\nline two\n\U0001f525 fire\n", encoding="utf-8")
        hits = _gate.scan([str(f)])
        assert len(hits) == 1
        assert hits[0].line == 3

    def test_case_insensitive_denylist(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("# CURRENT IMPLEMENTATION notes\n", encoding="utf-8")
        hits = _gate.scan([str(f)])
        assert any("current implementation" in h.reason for h in hits)

    def test_non_md_py_files_ignored(self, tmp_path: Path) -> None:
        """The scan function accepts whatever paths are passed; filtering is the caller's job.
        A .txt file with emoji is still flagged if passed explicitly."""
        f = tmp_path / "file.txt"
        f.write_text("✅ done\n", encoding="utf-8")
        # Pass explicitly — the file WILL be scanned
        hits = _gate.scan([str(f)])
        assert len(hits) >= 1


# ---------------------------------------------------------------------------
# Integration tests — subprocess entry point
# ---------------------------------------------------------------------------


class TestSubprocessGate:
    """Run check_hygiene.py via subprocess for full coverage of the entry point."""

    def test_clean_repo_exits_zero(self) -> None:
        """Running against the actual repo returns exit 0 (gate is clean)."""
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(_GATE_PATH)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"Hygiene gate returned non-zero on the clean repo.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "no violations found" in result.stdout

    def test_seeded_violation_exits_nonzero(self, tmp_path: Path) -> None:
        """A git-tracked .md file with a seeded violation causes exit 1."""
        # Initialise a real (minimal) git repo in tmp_path so git ls-files works.
        _git = ["git"]
        subprocess.run(  # noqa: S603
            [*_git, "init"],
            cwd=str(tmp_path),
            check=True,
            capture_output=True,
        )
        subprocess.run(  # noqa: S603
            [*_git, "config", "user.email", "test@test.com"],
            cwd=str(tmp_path),
            check=True,
            capture_output=True,
        )
        subprocess.run(  # noqa: S603
            [*_git, "config", "user.name", "Test"],
            cwd=str(tmp_path),
            check=True,
            capture_output=True,
        )

        # Seed a .md file with an emoji + denylist hit and stage it
        bad_md = tmp_path / "seeded.md"
        bad_md.write_text("\U0001f916 Generated with Claude\n", encoding="utf-8")
        subprocess.run(  # noqa: S603
            [*_git, "add", "seeded.md"],
            cwd=str(tmp_path),
            check=True,
            capture_output=True,
        )

        result = subprocess.run(  # noqa: S603
            [sys.executable, str(_GATE_PATH)],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            check=False,
        )
        assert result.returncode == 1, (
            f"Expected exit 1 for seeded violation, got {result.returncode}.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "violation" in result.stdout
        assert "docs/STYLE.md" in result.stdout
