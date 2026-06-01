"""AT-022 — Nielsen-10 usability-heuristic presence oracle (PRD v2.2 §12 E2 / R6).

The Nielsen critic votes **PRESENCE only** (a violation of a heuristic is present
or absent) and **never** assigns or acts on severity — severity is a human gate
(``<no_llm_severity_authority>`` / R6). Presence is decided by a **≥2/3 vote** of
three independent deterministic detectors per heuristic, so a single incidental
signal cannot trip a heuristic (the vote must be corroborated).

These tests are the AT-022 acceptance oracle. The **discrimination arm** is the
load-bearing one: a fixture that violates a known heuristic must fire the ≥2/3
presence vote for *that* heuristic, and the clean fixture must fire *no* heuristic.
The discrimination test FAILs on a stub :func:`evaluate_nielsen` (one that always
reports ABSENT, or always PRESENT) and only PASSes on the real detectors — proving
the oracle genuinely discriminates rather than vacuously agreeing.

PRD Reference: §12 AT-022 (Nielsen-10 critics), R6 (``<no_llm_severity_authority>``),
§3.2 (QA critique panel).
"""

from __future__ import annotations

import dataclasses
from uuid import uuid4

import pytest
from atelier.models.axis_weights import AxisWeights
from atelier.models.data_contracts import CandidateUI
from atelier.nodes.critique_panel import synthesize_panel
from atelier.nodes.nielsen import (
    PRESENCE_VOTE_THRESHOLD,
    VOTERS_PER_HEURISTIC,
    HeuristicVerdict,
    NielsenHeuristic,
    NielsenReport,
    evaluate_nielsen,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _candidate(html: str, css: str | None = None) -> CandidateUI:
    arts: dict[str, str] = {"index.html": html}
    if css is not None:
        arts["main.css"] = css
    return CandidateUI(candidate_id=uuid4(), surface_id=uuid4(), iteration=0, artifacts=arts)


def _doc(body: str, head_style: str = "") -> str:
    style = f"<style>{head_style}</style>" if head_style else ""
    return (
        f"<!DOCTYPE html><html lang='en'><head><title>Page</title>{style}</head>"
        f"<body>{body}</body></html>"
    )


# ---------------------------------------------------------------------------
# CLEAN fixture — a genuinely accessible, usable account-settings page.
# It follows every one of Nielsen's ten heuristics, so the oracle must report
# zero violations (every heuristic fires ≤1 of its three voters, i.e. < 2/3).
# ---------------------------------------------------------------------------

_CLEAN_STYLE = (
    ":root{--c-bg:#f4f1ea;--c-fg:#13293d;--c-primary:#1a3d5c;--c-accent:#e07a3f;--c-muted:#5a6b7a}"
    "body{color:var(--c-fg);background:var(--c-bg);font-family:'Inter',sans-serif;"
    "font-size:16px;line-height:1.6}"
    "h1{font-size:28px}h2{font-size:20px}small{font-size:13px}"
)

_CLEAN_BODY = (
    "<header role='banner'>"
    "<nav aria-label='Main'>"
    "<a href='/settings' aria-current='page'>Settings</a>"
    "<a href='/billing'>Billing</a>"
    "<a href='/help'>Help and FAQ</a>"
    "</nav>"
    "<button aria-label='Open menu'><svg aria-hidden='true' width='20' height='20'><rect/></svg></button>"
    "</header>"
    "<main id='main'>"
    "<a href='/dashboard'>Back to dashboard</a>"
    "<h1>Account settings</h1>"
    "<div role='status' aria-live='polite' class='toast'>Your changes are saved.</div>"
    "<div class='spinner' aria-hidden='true' hidden>Loading your profile, please wait.</div>"
    "<form action='/save' method='post'>"
    "<label for='name'>Full name</label>"
    "<input id='name' name='name' type='text' autocomplete='name' value='Ada Lovelace' required "
    "aria-describedby='name-hint' title='Your display name'>"
    "<small id='name-hint'>Shown on your public profile.</small>"
    "<label for='email'>Email address</label>"
    "<input id='email' name='email' type='email' autocomplete='email' value='ada@example.com' required "
    "pattern='[^@]+@[^@]+' aria-describedby='email-hint' title='We send receipts here'>"
    "<small id='email-hint'>We will never share your email. Check spelling before saving.</small>"
    "<label for='phone'>Phone</label>"
    "<input id='phone' name='phone' type='tel' autocomplete='tel' value='+1 555 0100' "
    "aria-describedby='phone-hint' title='Optional contact number'>"
    "<small id='phone-hint'>Used only for security alerts.</small>"
    "<div role='alert' class='error' hidden>"
    "Please check the highlighted fields and try again. Make sure your email is valid.</div>"
    "<button type='submit' accesskey='s'>Save changes</button>"
    "<button type='button'>Cancel</button>"
    "<p><small>Tip: press Alt and S (or Ctrl and S) to save quickly.</small></p>"
    "</form>"
    "<section aria-label='Danger zone'>"
    "<h2>Delete account</h2>"
    "<p>This permanently removes your workspace. You can export your data first.</p>"
    "<button type='button' aria-haspopup='dialog'>Delete account</button>"
    "</section>"
    "<dialog open aria-label='Confirm deletion'>"
    "<p>Are you sure you want to delete your account? This cannot be undone.</p>"
    "<button type='button'>Confirm delete</button>"
    "<button type='button'>Cancel</button>"
    "<button type='button' aria-label='Close dialog'>&times;</button>"
    "</dialog>"
    "<p><a href='/docs'>Read the documentation</a> or "
    "<a href='/help'>contact support</a> for help.</p>"
    "</main>"
    "<footer><p>Need help? Visit our help center anytime.</p></footer>"
)

CLEAN = _candidate(_doc(_CLEAN_BODY, _CLEAN_STYLE))


# ---------------------------------------------------------------------------
# VIOLATING fixtures — one realistic page per heuristic, each exhibiting ≥2 of
# the three deterministic violation signals for THAT heuristic. (They may also
# trip other heuristics — the acceptance only requires the target to fire and the
# CLEAN page to fire nothing; cross-heuristic purity is not asserted.)
# ---------------------------------------------------------------------------

_H1_NO_STATUS = _candidate(
    _doc(
        "<main><h1>Upload your report</h1>"
        "<form action='/upload' method='post'>"
        "<label for='f'>Report file</label><input id='f' type='file'>"
        "<button type='submit'>Upload</button>"
        "</form></main>"
    )
)

_H2_JARGON = _candidate(
    _doc(
        "<main><h1>Lorem Ipsum Dashboard</h1>"
        "<p>Lorem ipsum dolor sit amet. TODO: replace this placeholder copy.</p>"
        "<p>Current status: undefined (ERR_CODE_500). Saved value is null.</p>"
        "</main>"
    )
)

_H3_TRAP = _candidate(
    _doc(
        "<main><div role='dialog' aria-modal='true'>"
        "<h2>Subscribe to continue</h2>"
        "<p>Enter your email to keep reading.</p>"
        "<form><label for='e'>Email</label><input id='e' type='email'>"
        "<button type='submit'>Subscribe</button></form>"
        "</div></main>"
    )
)

_H4_INCONSISTENT = _candidate(
    _doc(
        "<main><h1>Actions</h1>"
        "<div onclick='save()'>Save</div>"
        "<a href='#' onclick='remove()'>Delete</a>"
        "<button onclick='edit()'>Edit</button>"
        "</main>"
    )
)

_H5_NO_PREVENTION = _candidate(
    _doc(
        "<main><h1>Account</h1>"
        "<form action='/save' method='post'>"
        "<label for='em'>Email</label><input id='em' type='text' name='email'>"
        "<label for='pw'>Password</label><input id='pw' type='text' name='password'>"
        "<button type='submit'>Save</button></form>"
        "<button>Delete account</button>"
        "</main>"
    )
)

_H6_RECALL = _candidate(
    _doc(
        "<main><nav><a href='/a'>A</a><a href='/b'>B</a></nav>"
        "<h1>Search</h1>"
        "<form><input type='text' placeholder='Query'>"
        "<input type='text' placeholder='Tags'>"
        "<button><svg width='16' height='16'><rect/></svg></button></form>"
        "</main>"
    )
)

_H7_INEFFICIENT = _candidate(
    _doc(
        "<main><h1>Checkout</h1>"
        "<form action='/pay' method='post'>"
        "<label for='n'>Name</label><input id='n' type='text' name='name'>"
        "<label for='e'>Email</label><input id='e' type='email' name='email'>"
        "<label for='a'>Address</label><input id='a' type='text' name='address'>"
        "<button type='submit'>Pay</button></form>"
        "</main>"
    )
)

_H8_CLUTTER = _candidate(
    _doc(
        "<main><h1>Deals</h1>"
        + "".join(f"<button>Buy {i}</button>" for i in range(14))
        + "</main>",
        head_style=(
            "".join(f".c{i}{{color:#{i:02x}{i:02x}{i:02x}}}" for i in range(1, 15))
            + "".join(f".s{i}{{font-size:{8 + i}px}}" for i in range(1, 11))
        ),
    )
)

_H9_BAD_ERRORS = _candidate(
    _doc(
        "<main><h1>Sign in</h1>"
        "<div role='alert'>Error 422</div>"
        "<form><label for='u'>User</label><input id='u' type='text'>"
        "<button type='submit'>Sign in</button></form>"
        "<p>Error: code 500</p>"
        "</main>"
    )
)

_H10_NO_HELP = _candidate(
    _doc(
        "<main><h1>Configure webhook</h1>"
        "<form action='/hooks' method='post'>"
        "<label for='url'>Endpoint URL</label><input id='url' type='url' name='url' required>"
        "<label for='sec'>Signing secret</label><input id='sec' type='text' name='secret' required>"
        "<label for='ev'>Events</label><input id='ev' type='text' name='events' required>"
        "<button type='submit'>Create webhook</button></form>"
        "</main>"
    )
)

VIOLATION_FIXTURES: tuple[tuple[NielsenHeuristic, CandidateUI, str], ...] = (
    (NielsenHeuristic.VISIBILITY_OF_SYSTEM_STATUS, _H1_NO_STATUS, "no-status-feedback"),
    (NielsenHeuristic.MATCH_SYSTEM_AND_REAL_WORLD, _H2_JARGON, "jargon-and-codes"),
    (NielsenHeuristic.USER_CONTROL_AND_FREEDOM, _H3_TRAP, "modal-with-no-exit"),
    (NielsenHeuristic.CONSISTENCY_AND_STANDARDS, _H4_INCONSISTENT, "nonstandard-controls"),
    (NielsenHeuristic.ERROR_PREVENTION, _H5_NO_PREVENTION, "no-constraints"),
    (NielsenHeuristic.RECOGNITION_RATHER_THAN_RECALL, _H6_RECALL, "placeholder-only"),
    (NielsenHeuristic.FLEXIBILITY_AND_EFFICIENCY, _H7_INEFFICIENT, "no-accelerators"),
    (NielsenHeuristic.AESTHETIC_AND_MINIMALIST, _H8_CLUTTER, "cluttered"),
    (NielsenHeuristic.HELP_RECOGNIZE_DIAGNOSE_RECOVER, _H9_BAD_ERRORS, "unhelpful-errors"),
    (NielsenHeuristic.HELP_AND_DOCUMENTATION, _H10_NO_HELP, "no-help"),
)


# ---------------------------------------------------------------------------
# Arm #1 — Structure & coverage
# ---------------------------------------------------------------------------


class TestStructure:
    """The report always covers all ten heuristics in a stable order."""

    def test_reports_exactly_ten_heuristics(self) -> None:
        report = evaluate_nielsen(CLEAN)
        assert len(report.verdicts) == 10
        assert {v.heuristic for v in report.verdicts} == set(NielsenHeuristic)

    def test_heuristic_order_is_stable_and_canonical(self) -> None:
        report = evaluate_nielsen(CLEAN)
        assert tuple(v.heuristic for v in report.verdicts) == tuple(NielsenHeuristic)

    def test_vote_constants_describe_a_two_thirds_rule(self) -> None:
        assert VOTERS_PER_HEURISTIC == 3
        assert PRESENCE_VOTE_THRESHOLD == 2  # ≥2 of 3


# ---------------------------------------------------------------------------
# Arm #2 — Discrimination (THE acceptance oracle, load-bearing)
# ---------------------------------------------------------------------------


class TestDiscrimination:
    """Violating fixtures fire their heuristic; the clean fixture fires none."""

    def test_clean_fixture_fires_no_heuristic(self) -> None:
        """The exemplary page must report ZERO violations across all ten heuristics."""
        report = evaluate_nielsen(CLEAN)
        present = report.violations
        assert present == (), "clean fixture wrongly flagged: " + ", ".join(
            f"{v.heuristic.value} ({v.votes}/3 via {v.voters_fired})"
            for v in report.verdicts
            if v.present
        )
        assert report.any_violation is False

    @pytest.mark.parametrize(
        ("heuristic", "candidate", "label"),
        [(h, c, lbl) for (h, c, lbl) in VIOLATION_FIXTURES],
        ids=[lbl for (_h, _c, lbl) in VIOLATION_FIXTURES],
    )
    def test_violating_fixture_fires_its_heuristic(
        self, heuristic: NielsenHeuristic, candidate: CandidateUI, label: str
    ) -> None:
        """A fixture violating heuristic H fires the ≥2/3 presence vote for H."""
        report = evaluate_nielsen(candidate)
        verdict = report.by_heuristic(heuristic)
        assert verdict.present is True, (
            f"[{label}] {heuristic.value} expected PRESENT, got ABSENT "
            f"({verdict.votes}/3 voters fired: {verdict.voters_fired})"
        )
        assert verdict.votes >= PRESENCE_VOTE_THRESHOLD, (
            f"[{label}] {heuristic.value} fired only {verdict.votes}/3 voters "
            f"(need ≥{PRESENCE_VOTE_THRESHOLD}): {verdict.voters_fired}"
        )

    @pytest.mark.parametrize(
        ("heuristic", "candidate", "label"),
        [(h, c, lbl) for (h, c, lbl) in VIOLATION_FIXTURES],
        ids=[lbl for (_h, _c, lbl) in VIOLATION_FIXTURES],
    )
    def test_clean_fixture_below_threshold_for_each_target(
        self, heuristic: NielsenHeuristic, candidate: CandidateUI, label: str
    ) -> None:
        """For every targeted heuristic, the clean page is strictly below the vote."""
        clean_verdict = evaluate_nielsen(CLEAN).by_heuristic(heuristic)
        assert clean_verdict.votes < PRESENCE_VOTE_THRESHOLD
        assert clean_verdict.present is False


# ---------------------------------------------------------------------------
# Arm #3 — No severity authority (R6 / <no_llm_severity_authority>)
# ---------------------------------------------------------------------------


class TestNoSeverityAuthority:
    """Presence only — the oracle never assigns or carries severity (R6)."""

    def test_verdict_has_no_severity_field(self) -> None:
        field_names = {f.name for f in dataclasses.fields(HeuristicVerdict)}
        assert "severity" not in field_names
        assert not any("sever" in name.lower() for name in field_names)

    def test_report_has_no_severity_field(self) -> None:
        field_names = {f.name for f in dataclasses.fields(NielsenReport)}
        assert not any("sever" in name.lower() for name in field_names)

    def test_presence_is_a_pure_boolean_vote(self) -> None:
        for verdict in evaluate_nielsen(_H5_NO_PREVENTION).verdicts:
            assert isinstance(verdict.present, bool)
            assert isinstance(verdict.votes, int)
            assert 0 <= verdict.votes <= VOTERS_PER_HEURISTIC
            # present iff the vote cleared the ≥2/3 threshold — never an ad-hoc severity.
            assert verdict.present == (verdict.votes >= PRESENCE_VOTE_THRESHOLD)

    def test_report_is_frozen(self) -> None:
        report = evaluate_nielsen(CLEAN)
        with pytest.raises(dataclasses.FrozenInstanceError):
            report.verdicts = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Arm #4 — Advisory, never gates convergence (R6: severity never auto-acts)
# ---------------------------------------------------------------------------


class TestAdvisoryNonGating:
    """A Nielsen violation is recorded but never blocks convergence by itself."""

    def _gate_clean_but_nielsen_violating(self) -> CandidateUI:
        """A rich, gate-clean, judge-passing page that also violates a heuristic.

        Reuses the AT-021 known-good ``_page`` recipe (var-token CSS + semantic
        body) so the deterministic gates and the D-O-R-A-V judges pass, then injects
        an H2 (match-real-world) violation — developer jargon in visible copy — which
        the gates and judges do not penalise.
        """
        css = (
            ":root{--color-primary:#1a3d5c;--color-bg:#f4f1ea;--color-fg:#13293d;"
            "--color-accent:#e07a3f;--space-sm:0.5rem;--space-md:1rem;"
            "--font-base:'Inter',sans-serif;--radius:8px}"
            "body{color:var(--color-fg);background:var(--color-bg);font-family:var(--font-base);"
            "font-size:18px;line-height:1.6;margin:0;padding:var(--space-md);letter-spacing:0.01em}"
            "header{display:flex;gap:var(--space-md)}nav a{padding:var(--space-sm);font-weight:600}"
            "main{display:grid;grid-template-columns:2fr 1fr;gap:var(--space-md)}"
            "h1{font-size:2.5rem;font-weight:800;margin:var(--space-md);color:var(--color-primary)}"
            "h2{font-size:1.5rem;font-weight:700}"
            "article{padding:var(--space-md);border-radius:var(--radius)}"
            "aside{background:var(--color-accent);padding:var(--space-md)}"
        )
        body = (
            "<header role='banner'>"
            "<nav aria-label='Main'><a href='#main'>Skip to content</a></nav>"
            "</header>"
            "<main id='main'>"
            "<article aria-labelledby='t'>"
            "<h1 id='t'>Quiet Co-working Spaces Designed for Deep Focus and Calm</h1>"
            "<p>Find a serene desk in a curated studio built for makers who need "
            "uninterrupted concentration and a welcoming community of peers.</p>"
            "<section aria-label='Features'>"
            "<h2>Why members stay with us</h2>"
            "<p>Ergonomic seating, soundproofed booths, barista coffee, and fast "
            "fibre internet across every floor.</p>"
            # H2 violation injected here — jargon / machine tokens in visible copy:
            "<p>TODO: replace debug output — current state is undefined and value is null.</p>"
            "</section>"
            "</article>"
            "<aside aria-label='Plans'>"
            "<h2>Membership plans</h2>"
            "<p>Flexible day passes and dedicated monthly desks tailored to your rhythm.</p>"
            "</aside>"
            "</main>"
            "<footer><img src='logo.png' alt='Studio logo'><p>Contact our team anytime.</p></footer>"
        )
        return _candidate(
            "<!DOCTYPE html><html lang='en'><head><title>Co</title></head><body>"
            + body
            + "</body></html>",
            css,
        )

    def test_nielsen_violation_does_not_block_convergence(self) -> None:
        candidate = self._gate_clean_but_nielsen_violating()
        report = evaluate_nielsen(candidate)
        assert report.any_violation is True, (
            "fixture must actually violate a heuristic for this test to be meaningful"
        )

        verdict = synthesize_panel(candidate, AxisWeights(), seed=7)
        assert verdict.passed is True, (
            "a Nielsen presence violation must NOT block convergence (R6: advisory, "
            f"severity is a human gate) — got passed=False (panel={verdict.panel_composite}, "
            f"raw={verdict.raw_composite}, floor={verdict.floor_passed}, "
            f"gate_failures={verdict.gate_failures})"
        )

    def test_panel_verdict_carries_advisory_nielsen_report(self) -> None:
        candidate = self._gate_clean_but_nielsen_violating()
        verdict = synthesize_panel(candidate, AxisWeights(), seed=7)
        assert isinstance(verdict.nielsen, NielsenReport)
        assert verdict.nielsen.any_violation is True
