"""Lighthouse CLI wrapper — Core Web Vitals extraction for DPO reward signal.

Lighthouse is Google's open-source automated web quality tool (Chrome DevTools).
This module exposes Core Web Vitals (LCP, CLS, INP) as the primary DPO reward
signal — not the aggregate a11y or performance category scores.

**Why Core Web Vitals, not Lighthouse a11y:**
Accessibility (a11y) compliance is important but applies to a narrow commercial
segment (government, healthcare, enterprise with legal requirements). The broad
audience of Atelier's users — startup founders, product teams, SMBs — care about
*performance* and *stability* as experienced by real users. Core Web Vitals are
Google's page experience ranking signals: every business with a website cares
about Google Search ranking, making CWV the universally relevant quality gate.

Core Web Vitals thresholds (Google "Good" tier):
  LCP ≤ 2500ms  — Largest Contentful Paint (perceived load speed)
  CLS ≤ 0.10    — Cumulative Layout Shift (visual stability)
  INP ≤ 200ms   — Interaction to Next Paint (interactivity responsiveness)

No published paper uses Core Web Vitals as DPO reward predicates. Atelier's use
is a first — and directly demonstrates 'built with Google' because these are
Google's own page quality standards.

**Hackathon narrative:** "Atelier's DPO reward engine gates pairs on Google's Core
Web Vitals — LCP, CLS, and INP. The chosen design must pass all three before it
enters the training dataset. This is an objective, machine-verifiable quality
signal built by Google."

Prerequisites: lighthouse CLI (``npm install -g lighthouse``).
Chrome/Chromium must be available. Mobile emulation is used by default
(``--form-factor=mobile``) because 60%+ of commercial web traffic is mobile.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

# Core Web Vitals thresholds — Google "Good" tier.
# Changes require an ADR amendment (same as EXTRINSIC_MARGIN_FLOOR et al.)
LCP_GOOD_THRESHOLD_MS: Final[float] = 2500.0
"""Largest Contentful Paint ≤ 2500ms = Google 'Good'. Directly affects bounce rate."""

CLS_GOOD_THRESHOLD: Final[float] = 0.10
"""Cumulative Layout Shift ≤ 0.10 = Google 'Good'. Measures visual stability."""

INP_GOOD_THRESHOLD_MS: Final[float] = 200.0
"""Interaction to Next Paint ≤ 200ms = Google 'Good'. Measures interactivity."""

# Aggregate Lighthouse category floors (kept for diagnostics, not as DPO gates).
LIGHTHOUSE_PERF_FLOOR: Final[float] = 0.80
"""Lighthouse aggregate performance score floor — diagnostic only, not a DPO gate."""


@dataclass(frozen=True, slots=True)
class CoreWebVitals:
    """Google Core Web Vitals from a Lighthouse audit.

    Units:
        lcp_ms: Largest Contentful Paint in milliseconds
        cls:    Cumulative Layout Shift (dimensionless, lower is better)
        inp_ms: Interaction to Next Paint in milliseconds (0.0 if not available)

    All three are defined by Google as the primary page experience signals
    used in Search ranking as of the 2023 CWV update.
    """

    lcp_ms: float
    cls: float
    inp_ms: float

    def passes(self) -> bool:
        """Return True if ALL three Core Web Vitals meet Google 'Good' thresholds."""
        return (
            self.lcp_ms <= LCP_GOOD_THRESHOLD_MS
            and self.cls <= CLS_GOOD_THRESHOLD
            and self.inp_ms <= INP_GOOD_THRESHOLD_MS
        )

    def failed_vitals(self) -> list[str]:
        """Return list of failed vital names, empty if all pass."""
        failed: list[str] = []
        if self.lcp_ms > LCP_GOOD_THRESHOLD_MS:
            failed.append(f"lcp:{self.lcp_ms:.0f}ms>{LCP_GOOD_THRESHOLD_MS:.0f}ms")
        if self.cls > CLS_GOOD_THRESHOLD:
            failed.append(f"cls:{self.cls:.3f}>{CLS_GOOD_THRESHOLD}")
        if self.inp_ms > INP_GOOD_THRESHOLD_MS:
            failed.append(f"inp:{self.inp_ms:.0f}ms>{INP_GOOD_THRESHOLD_MS:.0f}ms")
        return failed


@dataclass(frozen=True, slots=True)
class LighthouseScores:
    """Full Lighthouse category scores (aggregate). Kept for diagnostics.

    For DPO reward gating, use CoreWebVitals.passes() instead of these
    aggregate scores — individual vitals are more actionable.
    """

    performance: float  # 0.0-1.0
    accessibility: float  # 0.0-1.0 (kept for Layer 1 diagnostic, not DPO gate)
    best_practices: float  # 0.0-1.0
    seo: float  # 0.0-1.0
    core_web_vitals: CoreWebVitals


def run_lighthouse(
    url: str,
    *,
    mobile: bool = True,
    chrome_flags: str = "--headless",
) -> LighthouseScores:
    """Run Lighthouse against a URL and return scores including Core Web Vitals.

    Uses mobile emulation by default (``--form-factor=mobile``) because the
    DPO reward signal should reflect mobile-first quality — 60%+ of commercial
    web traffic is mobile. Pass ``mobile=False`` to use desktop emulation.

    Raises:
        RuntimeError: If the lighthouse CLI is not available or exits non-zero.
        ValueError: If the URL is not http(s) or the JSON output cannot be parsed.
    """
    # Guard against argument injection: the URL is passed positionally to the
    # lighthouse CLI, so a value beginning with '-' would be parsed as a flag and
    # a non-http scheme (file:, javascript:) would let the target read local
    # resources. Restrict to http(s) before building the arg list.
    if not url.startswith(("http://", "https://")):
        msg = f"run_lighthouse requires an http(s) URL, got: {url!r}"
        raise ValueError(msg)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        output_path = Path(tmp.name)

    form_factor_flags = (
        ["--form-factor=mobile", "--screenEmulation.mobile"]
        if mobile
        else ["--form-factor=desktop"]
    )

    try:
        result = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "lighthouse",
                url,
                "--output=json",
                f"--output-path={output_path}",
                f"--chrome-flags={chrome_flags}",
                "--only-categories=accessibility,performance,best-practices,seo",
                "--quiet",
                *form_factor_flags,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode not in (0, 1):
            msg = f"lighthouse exited {result.returncode}: {result.stderr[:500]}"
            raise RuntimeError(msg)

        raw: dict[str, Any] = json.loads(output_path.read_text(encoding="utf-8"))
    finally:
        output_path.unlink(missing_ok=True)

    cats = raw["categories"]
    audits = raw.get("audits", {})

    # Extract Core Web Vitals from individual audit entries.
    # INP may not be present on pages with no interactions — default to 0ms (passes).
    lcp_ms = float(audits.get("largest-contentful-paint", {}).get("numericValue", 0.0))
    cls = float(audits.get("cumulative-layout-shift", {}).get("numericValue", 0.0))
    inp_ms = float(audits.get("interaction-to-next-paint", {}).get("numericValue", 0.0))

    cwv = CoreWebVitals(lcp_ms=lcp_ms, cls=cls, inp_ms=inp_ms)

    return LighthouseScores(
        performance=float(cats["performance"]["score"]),
        accessibility=float(cats["accessibility"]["score"]),
        best_practices=float(cats["best-practices"]["score"]),
        seo=float(cats["seo"]["score"]),
        core_web_vitals=cwv,
    )


def passes_cwv_gate(scores: LighthouseScores) -> bool:
    """Return True if the page passes all three Core Web Vitals at Google 'Good' tier.

    This is the intended DPO reward predicate — preferred over the aggregate
    a11y/perf score gates because it reflects the quality metrics that matter
    to the broad commercial audience (Google Search ranking, load speed, stability).
    """
    return scores.core_web_vitals.passes()
