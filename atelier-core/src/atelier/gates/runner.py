"""Axis-filtered gate runner for the N3c pipeline stage.

Per PRD §6.3 N3c, a :class:`SurfaceState` declares which :class:`GateAxis`
values its candidates must satisfy via :attr:`SurfaceState.axes_required`.
This runner consults that list, dispatches only the relevant deterministic
gates, and aggregates their outcomes into a single :class:`GateRunResult`.

The runner is a pure-function orchestration layer: it owns no I/O, no state,
and no LLM calls. Its single responsibility is to map ``(candidate, axes)``
to ``GateRunResult`` so downstream code can make a clean PASS/REJECT decision
without inspecting individual outcomes.

PRD Reference: §6.3 N3c (Deterministic Gates)
ADR Reference: 0007 (worktree discipline) — Phase 1 scope only
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

from atelier.gates.deterministic import (
    check_axe_stub,
    check_css_validity,
    check_lighthouse_stub,
    check_semantic_html,
    check_token_fidelity,
    check_visual_diff_stub,
)
from atelier.models.data_contracts import CandidateUI, GateOutcome
from atelier.models.enums import GateAxis, GateDecision

# ---------------------------------------------------------------------------
# Axis → gate dispatch table
# ---------------------------------------------------------------------------

#: Mapping from :class:`GateAxis` to the corresponding deterministic gate
#: function. CSS validity rides on the LIGHTHOUSE_PERF axis (until a dedicated
#: axis exists), so a request for that axis runs the CSS-validity gate.
#:
#: The RESPONSIVE axis is intentionally absent from this table: Phase 1 does
#: not ship a responsive-design gate (browser rendering required). Requests
#: for unsupported axes are reported in :attr:`GateRunResult.unsupported_axes`.
_AXIS_TO_GATE: dict[GateAxis, Callable[[CandidateUI], GateOutcome]] = {
    GateAxis.SEMANTIC_HTML: check_semantic_html,
    GateAxis.LIGHTHOUSE_PERF: check_css_validity,
    GateAxis.TOKEN_FIDELITY: check_token_fidelity,
    GateAxis.LIGHTHOUSE_A11Y: check_lighthouse_stub,
    GateAxis.AXE: check_axe_stub,
    GateAxis.VISUAL_DIFF: check_visual_diff_stub,
}


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateRunResult:
    """Aggregated outcome of an axis-filtered gate run.

    A frozen dataclass keeps the runner output immutable without dragging
    Pydantic validation onto a purely-internal type. Consumers should treat
    this as a read-only snapshot of the gate stage.

    Attributes:
        candidate_id: The candidate that was evaluated.
        outcomes: Every :class:`GateOutcome` produced, in dispatch order.
        all_passed: ``True`` iff every outcome's decision is
            :attr:`GateDecision.PASS`. An empty ``outcomes`` list is also
            ``True`` (vacuously) — callers that require at least one gate
            should inspect ``len(outcomes)`` explicitly.
        failed_axes: The :class:`GateAxis` of every non-PASS outcome.
            Includes both REJECT and DEFER decisions.
        unsupported_axes: Axes that were requested but have no Phase 1
            implementation (e.g., :attr:`GateAxis.RESPONSIVE`). Logged for
            visibility; does not by itself fail the run.
    """

    candidate_id: UUID
    outcomes: list[GateOutcome]
    all_passed: bool
    failed_axes: list[GateAxis] = field(default_factory=list)
    unsupported_axes: list[GateAxis] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_gates(candidate: CandidateUI, axes_required: list[GateAxis]) -> GateRunResult:
    """Run the gates whose axes appear in ``axes_required``.

    Order of operations:
        1. De-duplicate ``axes_required`` while preserving first-seen order
           (callers occasionally pass the same axis twice; we run it once).
        2. For each axis, look up its gate in :data:`_AXIS_TO_GATE`.
           Unsupported axes are collected but skipped.
        3. Run the matched gates in order.
        4. Aggregate decisions into a :class:`GateRunResult`.

    Args:
        candidate: The :class:`CandidateUI` to evaluate.
        axes_required: The list of :class:`GateAxis` values to run, typically
            sourced from :attr:`SurfaceState.axes_required`. An empty list
            produces a vacuously-passing result with no outcomes.

    Returns:
        A :class:`GateRunResult` capturing every outcome, the overall pass
        flag, the axes that failed, and any unsupported axes that were
        silently skipped.

    Examples:
        >>> from uuid import uuid4
        >>> cand = CandidateUI(
        ...     candidate_id=uuid4(),
        ...     surface_id=uuid4(),
        ...     iteration=0,
        ...     artifacts={
        ...         "index.html": "<header></header><main></main><nav></nav>",
        ...     },
        ... )
        >>> result = run_gates(cand, [GateAxis.SEMANTIC_HTML])
        >>> result.all_passed
        True
    """
    seen: set[GateAxis] = set()
    unique_axes: list[GateAxis] = []
    for axis in axes_required:
        if axis not in seen:
            seen.add(axis)
            unique_axes.append(axis)

    outcomes: list[GateOutcome] = []
    unsupported: list[GateAxis] = []
    for axis in unique_axes:
        gate = _AXIS_TO_GATE.get(axis)
        if gate is None:
            unsupported.append(axis)
            continue
        outcomes.append(gate(candidate))

    failed = [outcome.axis for outcome in outcomes if outcome.decision is not GateDecision.PASS]
    return GateRunResult(
        candidate_id=candidate.candidate_id,
        outcomes=outcomes,
        all_passed=not failed,
        failed_axes=failed,
        unsupported_axes=unsupported,
    )


class GateRunner:
    """Stateful façade around :func:`run_gates` for dependency-injection sites.

    Most callers should prefer :func:`run_gates` directly. This class exists
    for sites that want to inject a configured runner (e.g., the ADK agent
    factory) without leaking the module-level dispatch table.

    Attributes:
        axes_required: Default axes to evaluate when none are passed to
            :meth:`run`.
    """

    def __init__(self, axes_required: list[GateAxis] | None = None) -> None:
        """Initialize the runner with a default axis list.

        Args:
            axes_required: Default axes to evaluate. If ``None``, every axis
                with a Phase 1 implementation is run.
        """
        self.axes_required: list[GateAxis] = (
            axes_required if axes_required is not None else list(_AXIS_TO_GATE.keys())
        )

    def run(
        self,
        candidate: CandidateUI,
        axes_required: list[GateAxis] | None = None,
    ) -> GateRunResult:
        """Evaluate ``candidate`` against ``axes_required`` (or the default).

        Args:
            candidate: The :class:`CandidateUI` to evaluate.
            axes_required: Overrides the instance default if provided.

        Returns:
            The :class:`GateRunResult` from :func:`run_gates`.
        """
        axes = axes_required if axes_required is not None else self.axes_required
        return run_gates(candidate, axes)
