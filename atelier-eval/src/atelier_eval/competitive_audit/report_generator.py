"""Markdown report generator for competitive audit results.

Generates a structured markdown report with embedded image links,
summary tables, pass/fail indicators, and per-product detail sections.
Report format aligns with Atelier's audit/ directory convention
(see audit/YYYY-MM-DD-competitive/report.md).

Design decisions:
  - Markdown output (not HTML/PDF) for git-friendliness and diff-ability.
  - Embeds screenshot paths as relative markdown image links.
  - Uses GitHub-style alerts for critical findings.
  - Produces both a summary table and per-product detail sections.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from io import StringIO
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from atelier_eval.competitive_audit.error_capture import ErrorCaptureResult
    from atelier_eval.competitive_audit.screenshot_capture import ScreenshotCaptureResult

from atelier_eval.competitive_audit.config import (
    CWV_THRESHOLDS,
    LIGHTHOUSE_THRESHOLDS,
    MAX_ERROR_TEXT_LENGTH,
    MAX_ERRORS_IN_REPORT,
    MAX_URL_LENGTH_IN_REPORT,
    Product,
)
from atelier_eval.competitive_audit.lighthouse_capture import (
    LighthouseCapture,
    evaluate_cwv,
    evaluate_thresholds,
)

logger = logging.getLogger(__name__)


@dataclass
class ProductAuditResult:
    """Complete audit data for a single product."""

    product: Product
    lighthouse: LighthouseCapture | None = None
    errors: ErrorCaptureResult | None = None
    screenshots: ScreenshotCaptureResult | None = None
    audit_timestamp: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat()
    )


def generate_report(
    results: list[ProductAuditResult],
    output_path: Path,
    *,
    title: str = "Competitive Browser UI/UX Audit",
) -> Path:
    """Generate a markdown report from audit results.

    Args:
        results: List of per-product audit results.
        output_path: Path to write the report markdown file.
        title: Report title.

    Returns:
        Path to the generated report.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    buf = StringIO()

    _write_header(buf, title, results)
    _write_summary_table(buf, results)
    _write_cwv_summary(buf, results)
    _write_error_summary(buf, results)

    for result in results:
        _write_product_detail(buf, result, output_path.parent)

    _write_footer(buf)

    report_text = buf.getvalue()
    output_path.write_text(report_text, encoding="utf-8")
    logger.info("Report written to %s (%d bytes)", output_path, len(report_text))
    return output_path


def _write_header(buf: StringIO, title: str, results: list[ProductAuditResult]) -> None:
    """Write the report header with metadata."""
    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M UTC")
    product_names = ", ".join(r.product.name for r in results)

    buf.write(f"# {title}\n\n")
    buf.write(f"> **Generated:** {timestamp}  \n")
    buf.write(f"> **Products:** {product_names}  \n")
    buf.write(f"> **Thresholds:** Lighthouse >={LIGHTHOUSE_THRESHOLDS.performance} (perf), ")
    buf.write(f">={LIGHTHOUSE_THRESHOLDS.accessibility} (a11y), ")
    buf.write(f">={LIGHTHOUSE_THRESHOLDS.best_practices} (BP)  \n")
    buf.write(f"> **CWV Good:** LCP <={CWV_THRESHOLDS.lcp_good_ms}ms, ")
    buf.write(f"CLS <={CWV_THRESHOLDS.cls_good}, INP <={CWV_THRESHOLDS.inp_good_ms}ms\n\n")
    buf.write("---\n\n")


def _write_summary_table(buf: StringIO, results: list[ProductAuditResult]) -> None:
    """Write the Lighthouse summary comparison table."""
    buf.write("## Lighthouse Summary\n\n")
    buf.write("| Product | Perf | A11y | Best Practices | SEO | Pass? |\n")
    buf.write("| --- | --- | --- | --- | --- | --- |\n")

    for r in results:
        if r.lighthouse and r.lighthouse.lighthouse_median:
            lh = r.lighthouse.lighthouse_median
            thresholds = evaluate_thresholds(lh)
            all_pass = all(thresholds.values())
            icon = "PASS" if all_pass else "FAIL"

            buf.write(
                f"| **{r.product.name}** "
                f"| {lh.performance:.0f} "
                f"| {lh.accessibility:.0f} "
                f"| {lh.best_practices:.0f} "
                f"| {lh.seo:.0f} "
                f"| {icon} |\n"
            )
        else:
            buf.write(f"| **{r.product.name}** | -- | -- | -- | -- | Skipped |\n")

    buf.write("\n")


def _write_cwv_summary(buf: StringIO, results: list[ProductAuditResult]) -> None:
    """Write the Core Web Vitals comparison table."""
    buf.write("## Core Web Vitals\n\n")
    buf.write("| Product | LCP (ms) | CLS | INP (ms) | TTFB (ms) | FCP (ms) |\n")
    buf.write("| --- | --- | --- | --- | --- | --- |\n")

    for r in results:
        if r.lighthouse and r.lighthouse.cwv:
            cwv = r.lighthouse.cwv
            ratings = evaluate_cwv(cwv)

            def _fmt(value: float, rating: str) -> str:
                labels = {"good": "[good]", "needs-improvement": "[warn]", "poor": "[poor]"}
                label = labels.get(rating, "[--]")
                return f"{label} {value:.0f}"

            buf.write(
                f"| **{r.product.name}** "
                f"| {_fmt(cwv.lcp_ms, ratings['lcp'])} "
                f"| {_fmt(cwv.cls, ratings['cls'])} "
                f"| {_fmt(cwv.inp_ms, ratings['inp'])} "
                f"| {cwv.ttfb_ms:.0f} "
                f"| {cwv.fcp_ms:.0f} |\n"
            )
        else:
            buf.write(f"| **{r.product.name}** | -- | -- | -- | -- | -- |\n")

    buf.write("\n")


def _write_error_summary(buf: StringIO, results: list[ProductAuditResult]) -> None:
    """Write the error summary comparison table."""
    buf.write("## Console Errors & Network Failures\n\n")
    buf.write("| Product | JS Errors | Warnings | Page Crashes | Failed Requests | Critical? |\n")
    buf.write("| --- | --- | --- | --- | --- | --- |\n")

    for r in results:
        if r.errors:
            e = r.errors
            status = "CRITICAL" if e.has_critical_issues else "OK"
            buf.write(
                f"| **{r.product.name}** "
                f"| {e.total_errors} "
                f"| {e.total_warnings} "
                f"| {len(e.page_errors)} "
                f"| {e.total_network_failures} "
                f"| {status} |\n"
            )
        else:
            buf.write(f"| **{r.product.name}** | -- | -- | -- | -- | Skipped |\n")

    buf.write("\n")


def _write_product_detail(
    buf: StringIO,
    result: ProductAuditResult,
    report_dir: Path,
) -> None:
    """Write detailed per-product section."""
    buf.write(f"---\n\n## {result.product.name}\n\n")
    buf.write(f"- **URL:** `{result.product.url}`\n")
    buf.write(f"- **Category:** {result.product.category}\n")
    buf.write(f"- **Reason:** {result.product.reason}\n")
    if result.product.requires_auth:
        buf.write(f"- **Auth Required:** {result.product.auth_note}\n")
    buf.write(f"- **Audited:** {result.audit_timestamp}\n\n")

    # Errors detail.
    if result.errors and result.errors.has_critical_issues:
        buf.write("> [!WARNING]\n")
        buf.write(f"> {result.errors.total_errors} JS error(s) detected.\n\n")

        if result.errors.console_errors:
            buf.write("### Console Errors\n\n")
            for err in result.errors.console_errors[:MAX_ERRORS_IN_REPORT]:
                buf.write(f"- `{err.text[:MAX_ERROR_TEXT_LENGTH]}`\n")
            overflow = len(result.errors.console_errors) - MAX_ERRORS_IN_REPORT
            if overflow > 0:
                buf.write(f"- ... and {overflow} more\n")
            buf.write("\n")

        if result.errors.network_failures:
            buf.write("### Failed Network Requests\n\n")
            for nf in result.errors.network_failures[:MAX_ERRORS_IN_REPORT]:
                buf.write(
                    f"- `{nf.method} {nf.url[:MAX_URL_LENGTH_IN_REPORT]}` "
                    f"-> **{nf.status}** {nf.status_text}\n"
                )
            buf.write("\n")

    # Screenshots.
    if result.screenshots and result.screenshots.screenshots:
        buf.write("### Responsive Screenshots\n\n")
        for ss in result.screenshots.screenshots:
            rel_path = _relative_path(ss.file_path, report_dir)
            buf.write(f"#### {ss.breakpoint_label} ({ss.width}x{ss.height})\n\n")
            buf.write(f"![{result.product.name} {ss.breakpoint_label}]({rel_path})\n\n")

    buf.write("\n")


def _write_footer(buf: StringIO) -> None:
    """Write the report footer."""
    buf.write("---\n\n")
    buf.write("*Report generated by `atelier-eval` competitive audit module.*  \n")
    buf.write("*Methodology: [docs/eval/methodology.md](../../docs/eval/methodology.md) ")
    buf.write("Competitive comparative audit*\n")


def _relative_path(target: Path, base: Path) -> str:
    """Compute a relative path from base to target, for markdown links."""
    try:
        return str(target.relative_to(base))
    except ValueError:
        return str(target)
