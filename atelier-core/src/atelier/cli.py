"""Atelier CLI — ``atelier`` command-line interface.

Subcommands:
    generate  — Run the full design pipeline from a brief (N1 → N3a).
    gates     — Run all deterministic gates against an HTML artifact.
    evaluate  — Evaluate an HTML file against the D-O-R-A-V judge suite.
    version   — Print version and exit.

Usage examples::

    atelier generate --brief "Build a dashboard for SaaS analytics" --out ./output
    atelier gates --html ./output/index.html
    atelier evaluate --html ./output/index.html
    atelier version
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from atelier.__version__ import __version__

_BANNER = f"Atelier v{__version__} — Autonomous Design Agent"


# ---------------------------------------------------------------------------
# Subcommand: version
# ---------------------------------------------------------------------------


def cmd_version(_args: argparse.Namespace) -> int:
    """Print version information."""
    print(_BANNER)
    print(f"  Python:      {sys.version.split()[0]}")
    print(f"  Entry point: {Path(__file__).resolve()}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: gates
# ---------------------------------------------------------------------------


def cmd_gates(args: argparse.Namespace) -> int:
    """Run all deterministic gates against an HTML artifact and print results."""
    from uuid import uuid4

    from atelier.gates.deterministic import run_all_gates
    from atelier.models.data_contracts import CandidateUI
    from atelier.models.enums import GateDecision

    html_path = Path(args.html)
    if not html_path.exists():
        print(f"Error: {html_path} does not exist.", file=sys.stderr)
        return 1

    artifacts: dict[str, Any] = {"index.html": html_path.read_text(encoding="utf-8")}

    # Include sibling CSS files
    for css_file in html_path.parent.glob("*.css"):
        artifacts[css_file.name] = css_file.read_text(encoding="utf-8")

    candidate = CandidateUI(
        candidate_id=uuid4(),
        surface_id=uuid4(),
        iteration=0,
        artifacts=artifacts,
    )

    outcomes = run_all_gates(candidate)

    passed = sum(1 for o in outcomes if o.decision == GateDecision.PASS)
    total = len(outcomes)
    print(f"\nGate results for: {html_path}")
    print(f"{'─' * 60}")
    for outcome in outcomes:
        icon = "PASS" if outcome.decision == GateDecision.PASS else "FAIL"
        print(
            f"  [{icon}] {outcome.axis.value:20s}  score={outcome.score:6.1f}  {outcome.diagnostic[:60]}"
        )
    print(f"{'─' * 60}")
    print(f"  {passed}/{total} gates passed")

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "axis": o.axis.value,
                        "decision": o.decision.value,
                        "score": o.score,
                        "diagnostic": o.diagnostic,
                    }
                    for o in outcomes
                ],
                indent=2,
            )
        )

    return 0 if passed == total else 1


# ---------------------------------------------------------------------------
# Subcommand: evaluate
# ---------------------------------------------------------------------------


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Run D-O-R-A-V consensus evaluation against an HTML file."""
    from uuid import uuid4

    from atelier.models.axis_weights import AxisWeights
    from atelier.models.data_contracts import CandidateUI
    from atelier.nodes.consensus import evaluate_candidate

    html_path = Path(args.html)
    if not html_path.exists():
        print(f"Error: {html_path} does not exist.", file=sys.stderr)
        return 1

    artifacts: dict[str, Any] = {"index.html": html_path.read_text(encoding="utf-8")}
    for css_file in html_path.parent.glob("*.css"):
        artifacts[css_file.name] = css_file.read_text(encoding="utf-8")

    candidate = CandidateUI(
        candidate_id=uuid4(),
        surface_id=uuid4(),
        iteration=0,
        artifacts=artifacts,
    )

    weights = AxisWeights()
    evaluation = evaluate_candidate(candidate, weights)

    print(f"\nD-O-R-A-V Evaluation: {html_path}")
    print(f"{'─' * 60}")
    print(f"  Composite score:  {evaluation.composite_score:.3f}")
    print(f"  Passed:           {'YES' if evaluation.passed else 'NO'}")
    print(f"{'─' * 60}")
    for axis, vote in evaluation.votes.items():
        print(f"  {axis.value:20s}  {vote.score:.3f}  {vote.reasoning[:50]}")

    if args.json:
        print(
            json.dumps(
                {
                    "composite_score": evaluation.composite_score,
                    "passed": evaluation.passed,
                    "votes": {
                        axis.value: {"score": v.score, "reasoning": v.reasoning}
                        for axis, v in evaluation.votes.items()
                    },
                },
                indent=2,
            )
        )

    return 0


# ---------------------------------------------------------------------------
# Subcommand: generate
# ---------------------------------------------------------------------------


def cmd_generate(args: argparse.Namespace) -> int:
    """Run the full design pipeline from a brief text."""
    from atelier.models.data_contracts import TenantContext
    from atelier.orchestrator.runner import AtelierRunner

    async def _run() -> dict[str, Any]:
        runner = AtelierRunner()
        tenant_ctx = TenantContext(
            tenant_id=args.tenant_id,
            user_id=args.user_id,
            project_id=args.project_id,
        )
        return await runner.run(args.brief, tenant_ctx)

    print(f"\nAtelier — Generating design for brief: {args.brief[:80]}")
    print(f"  Tenant: {args.tenant_id} / User: {args.user_id}")
    print("  Usage cap: per-user lifetime 5,000,000-token cap (AT-095)")
    print(f"{'─' * 60}")

    try:
        result = asyncio.run(_run())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"Pipeline error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    candidates = result.get("candidates", [])
    session_id = result.get("session_id", "unknown")
    stitch_degraded = result.get("stitch_degraded", False)

    print(f"  Session ID:     {session_id}")
    print(f"  Candidates:     {len(candidates)}")
    print(f"  Stitch:         {'degraded (fallback mode)' if stitch_degraded else 'OK'}")

    if result.get("user_message"):
        print(f"  Notice:         {result['user_message']}")

    out_dir = Path(args.out) if args.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, candidate in enumerate(candidates):
            content = candidate if isinstance(candidate, str) else str(candidate)
            out_file = out_dir / f"candidate_{i + 1}.html"
            out_file.write_text(content, encoding="utf-8")
            print(f"  Wrote:          {out_file}")

    if args.json:
        print(
            json.dumps(
                {
                    "session_id": session_id,
                    "candidate_count": len(candidates),
                    "stitch_degraded": stitch_degraded,
                    "user_message": result.get("user_message"),
                },
                indent=2,
            )
        )

    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atelier",
        description=_BANNER,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  atelier generate --brief 'Build a SaaS analytics dashboard'\n"
            "  atelier gates --html ./output/index.html\n"
            "  atelier evaluate --html ./output/index.html\n"
            "  atelier version\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = False

    # version
    sub.add_parser("version", help="Print version and exit")

    # gates
    p_gates = sub.add_parser("gates", help="Run deterministic gates on an HTML artifact")
    p_gates.add_argument("--html", required=True, metavar="FILE", help="Path to index.html")
    p_gates.add_argument("--json", action="store_true", help="Also emit JSON results")

    # evaluate
    p_eval = sub.add_parser("evaluate", help="Run D-O-R-A-V consensus evaluation")
    p_eval.add_argument("--html", required=True, metavar="FILE", help="Path to index.html")
    p_eval.add_argument("--json", action="store_true", help="Also emit JSON results")

    # generate
    p_gen = sub.add_parser("generate", help="Run the full design pipeline from a brief")
    p_gen.add_argument("--brief", required=True, metavar="TEXT", help="Design brief text")
    p_gen.add_argument("--out", metavar="DIR", help="Output directory for generated candidates")
    p_gen.add_argument("--tenant-id", default="cli-user", metavar="ID")
    p_gen.add_argument("--user-id", default="cli-user", metavar="ID")
    p_gen.add_argument("--project-id", default="cli-project", metavar="ID")
    # AT-095: the --budget USD flag is removed; usage is governed by the per-user
    # lifetime 5M-token cap (server-side), not a per-run dollar budget.
    p_gen.add_argument("--json", action="store_true", help="Also emit JSON summary")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the ``atelier`` console script."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        print(_BANNER)
        print("\nRun ``atelier --help`` for available commands.\n")
        sys.exit(0)

    dispatch = {
        "version": cmd_version,
        "gates": cmd_gates,
        "evaluate": cmd_evaluate,
        "generate": cmd_generate,
    }
    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    sys.exit(handler(args))


if __name__ == "__main__":
    main()
