"""Fail-closed gate-before-emit for the Governed A2UI surface (G2, ADR-0024 §2).

Pure, deterministic, browser-free validation of an A2UI server-to-client message
list **before** it is emitted to the frontend renderer. The posture is
**fail-closed**: any validation failure → REJECT, and the caller substitutes a
custom governance event list (``governance_messages``) for the rejected surface —
the off-brand / inaccessible surface is never shipped.

The single entry point is :func:`gate_a2ui_surface`. It runs four deterministic
validators, each reusing or paralleling an existing Atelier gate:

1. **envelope**   — structural floor: every message is a dict carrying
   ``version == "v0.9"`` and exactly one of the four known message keys; the
   ``updateComponents`` message carries a non-empty ``components`` array with
   exactly one ``id == "root"`` (mirrors the ``server_to_client.json`` ``oneOf`` /
   the frontend ``A2uiMessage`` union the renderer would otherwise reject).
2. **catalog**    — allowlist + required-prop contract: every component's
   ``component`` type is a key in the Atelier catalog allowlist
   (:data:`atelier.a2ui.catalog.ALLOWED_COMPONENTS`) AND carries every required
   prop for its type. An out-of-catalog component or a missing required prop →
   REJECT with the RFC-6901 JSON pointer to the offending component.
3. **accessible_name** — every component that declares an ``accessibility`` block
   must give it a non-empty ``label`` (or ``description``). A label-less control
   would render without an accessible name; fail-closed catches it the moment an
   agent emits one. (The current ``Text``-only design-system panel passes
   trivially — no ``accessibility`` blocks declared.)
4. **contrast**   — AA contrast on inferable foreground/background token PAIRS in
   the ``/tokens`` data model, reusing :mod:`atelier.gates.contrast` primitives
   (:func:`_parse_color`, :func:`_contrast_ratio`, :data:`_AA_NORMAL_RATIO`).
   Honest scope: where no fg/bg pair can be inferred this validator is a no-op
   PASS (matching ``contrast.py``'s "no explicit pairs → PASS, cascade is axe's
   job"). Any inferable pair below AA → REJECT naming both tokens + the ratio.

On REJECT the gate returns :class:`A2uiGateResult` carrying the structured
``reasons`` and a ``governance_messages`` list: one custom A2UI event
(``atelier/governance.rejected``) embedding a ``VALIDATION_FAILED`` diagnostic per
the A2UI failure-report shape. The caller emits ``governance_messages`` instead of
the surface and sets ``a2ui_payload = []`` so the frontend's existing fail-soft
fallback (empty renderable list → hand-built panel) engages.

NOTE on ``VALIDATION_FAILED`` provenance (ADR-0024 honest-claim boundary): the
A2UI wire ``VALIDATION_FAILED`` error is *client→server*. We repurpose its SHAPE
inside a server-emitted custom event payload as the machine-readable self-report.
It is the failure-report shape, NOT a wire-conformance claim.

This module is PURE: no I/O, no LLM, no network, no browser. Structured logging
only; no silent error suppression.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from atelier.a2ui.catalog import ALLOWED_COMPONENTS
from atelier.gates.contrast import _AA_NORMAL_RATIO, _contrast_ratio, _parse_color

logger = logging.getLogger(__name__)

#: The four known A2UI server-to-client message keys (exactly one per message).
_KNOWN_MESSAGE_KEYS: frozenset[str] = frozenset(
    {"createSurface", "updateComponents", "updateDataModel", "deleteSurface"}
)

#: The wire version every message must carry (mirrors
#: :data:`atelier.a2ui.surface.A2UI_WIRE_VERSION`; redeclared as a literal so the
#: gate has no import-time dependency on the surface builder).
_A2UI_WIRE_VERSION: str = "v0.9"

#: The gate label carried in every governance event (ADR-0024 §2).
_GATE_NAME: str = "governed-a2ui"

#: The governance custom-event name the frontend keys its governance banner on.
_GOVERNANCE_EVENT_NAME: str = "atelier/governance.rejected"

#: Token-name suffixes used to infer a foreground/background contrast pair from
#: the flat ``/tokens`` rows (DTCG convention). A row whose ``path`` ends in one of
#: the foreground suffixes is paired with a same-prefix background row.
_FOREGROUND_SUFFIXES: tuple[str, ...] = ("-foreground", "-text", "-on-surface", "-on-background")
_BACKGROUND_SUFFIXES: tuple[str, ...] = ("-background", "-surface", "-bg")


@dataclass(frozen=True)
class A2uiRejectReason:
    """A single structured reason a surface was REJECTed.

    Attributes:
        validator: Which validator fired —
            ``"envelope" | "catalog" | "accessible_name" | "contrast"``.
        json_pointer: RFC-6901 pointer into the message list locating the offending
            node (e.g. ``"/1/updateComponents/components/5/component"``).
        message: One/two-sentence human-readable reason.
    """

    validator: str
    json_pointer: str
    message: str


@dataclass(frozen=True)
class A2uiGateResult:
    """The outcome of gating an A2UI surface.

    Attributes:
        passed: ``True`` iff every validator passed.
        reasons: Structured REJECT reasons; empty iff ``passed``.
        governance_messages: The custom governance event(s) the caller emits
            INSTEAD of the rejected surface; empty iff ``passed``.
    """

    passed: bool
    reasons: list[A2uiRejectReason] = field(default_factory=list)
    governance_messages: list[dict[str, Any]] = field(default_factory=list)


def _iter_component_messages(
    messages: list[Any],
) -> list[tuple[int, list[Any]]]:
    """Yield ``(message_index, components_list)`` for each ``updateComponents`` msg.

    Args:
        messages: The full A2UI message list.

    Returns:
        A list of ``(index, components)`` tuples; ``components`` is whatever the
        message carried (validated by the envelope check, so callers may assume a
        list here only after envelope passed — this helper is tolerant and skips
        non-list ``components``).
    """
    out: list[tuple[int, list[Any]]] = []
    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            continue
        update = msg.get("updateComponents")
        if not isinstance(update, dict):
            continue
        components = update.get("components")
        if isinstance(components, list):
            out.append((idx, components))
    return out


def _validate_envelope(messages: list[Any]) -> list[A2uiRejectReason]:
    """Validate the structural envelope of the message list (fail-closed floor).

    Rejects: an empty list; a non-dict message; a message missing the ``version``
    const or carrying the wrong one; a message that does not carry exactly one of
    the four known message keys; an ``updateComponents`` whose ``components`` is not
    a non-empty list with exactly one ``id == "root"``.

    Args:
        messages: The A2UI message list.

    Returns:
        A list of :class:`A2uiRejectReason` (empty iff the envelope is valid).
    """
    reasons: list[A2uiRejectReason] = []

    if not messages:
        reasons.append(
            A2uiRejectReason(
                validator="envelope",
                json_pointer="",
                message="Empty A2UI surface: at least createSurface + updateComponents are required.",
            )
        )
        return reasons

    for idx, msg in enumerate(messages):
        ptr = f"/{idx}"
        if not isinstance(msg, dict):
            reasons.append(
                A2uiRejectReason(
                    validator="envelope",
                    json_pointer=ptr,
                    message=f"Message at index {idx} is not an object.",
                )
            )
            continue
        if msg.get("version") != _A2UI_WIRE_VERSION:
            reasons.append(
                A2uiRejectReason(
                    validator="envelope",
                    json_pointer=f"{ptr}/version",
                    message=(
                        f"Message version must be {_A2UI_WIRE_VERSION!r}, "
                        f"got {msg.get('version')!r}."
                    ),
                )
            )
        present_keys = _KNOWN_MESSAGE_KEYS & set(msg.keys())
        if len(present_keys) != 1:
            reasons.append(
                A2uiRejectReason(
                    validator="envelope",
                    json_pointer=ptr,
                    message=(
                        "Each message must carry exactly one of "
                        f"{sorted(_KNOWN_MESSAGE_KEYS)}; found {sorted(present_keys)}."
                    ),
                )
            )

    # updateComponents structural rules (non-empty components, exactly one root).
    for idx, components in _iter_component_messages(messages):
        comp_ptr = f"/{idx}/updateComponents/components"
        if not components:
            reasons.append(
                A2uiRejectReason(
                    validator="envelope",
                    json_pointer=comp_ptr,
                    message="updateComponents.components must be a non-empty array.",
                )
            )
            continue
        root_count = sum(1 for c in components if isinstance(c, dict) and c.get("id") == "root")
        if root_count != 1:
            reasons.append(
                A2uiRejectReason(
                    validator="envelope",
                    json_pointer=comp_ptr,
                    message=(
                        "updateComponents.components must contain exactly one "
                        f"component with id == 'root'; found {root_count}."
                    ),
                )
            )

    return reasons


def _validate_catalog(
    messages: list[Any],
    allowed: Mapping[str, frozenset[str]],
) -> list[A2uiRejectReason]:
    """Validate every component against the catalog allowlist + required props.

    Args:
        messages: The A2UI message list.
        allowed: ``componentType -> frozenset[required-prop-names]`` — the catalog
            allowlist. ``allowed.keys()`` is the trusted component set; a component
            type outside it is REJECTed.

    Returns:
        A list of :class:`A2uiRejectReason` (empty iff every component is in the
        allowlist and carries its required props).
    """
    reasons: list[A2uiRejectReason] = []
    for msg_idx, components in _iter_component_messages(messages):
        for comp_idx, comp in enumerate(components):
            base = f"/{msg_idx}/updateComponents/components/{comp_idx}"
            if not isinstance(comp, dict):
                reasons.append(
                    A2uiRejectReason(
                        validator="catalog",
                        json_pointer=base,
                        message=f"Component at {base} is not an object.",
                    )
                )
                continue
            ctype = comp.get("component")
            if not isinstance(ctype, str) or ctype not in allowed:
                reasons.append(
                    A2uiRejectReason(
                        validator="catalog",
                        json_pointer=f"{base}/component",
                        message=(
                            f"Component type {ctype!r} is not in the Atelier catalog "
                            f"allowlist {sorted(allowed.keys())} (fail-closed)."
                        ),
                    )
                )
                continue
            for required_prop in sorted(allowed[ctype]):
                if required_prop not in comp:
                    reasons.append(
                        A2uiRejectReason(
                            validator="catalog",
                            json_pointer=base,
                            message=(
                                f"{ctype} component is missing required prop {required_prop!r}."
                            ),
                        )
                    )
    return reasons


def _validate_accessible_names(
    messages: list[Any],
) -> list[A2uiRejectReason]:
    """Validate that every declared ``accessibility`` block has a non-empty name.

    A component MAY omit ``accessibility`` entirely (the design-system panel's
    ``Text`` nodes do — their literal/bound ``text`` is the accessible name). But if
    a component DECLARES an ``accessibility`` block, that block must carry a
    non-empty ``label`` or ``description`` — an empty accessible name is worse than
    none (it suppresses the content fallback).

    Args:
        messages: The A2UI message list.

    Returns:
        A list of :class:`A2uiRejectReason` (empty iff every declared
        ``accessibility`` block names the component).
    """
    reasons: list[A2uiRejectReason] = []
    for msg_idx, components in _iter_component_messages(messages):
        for comp_idx, comp in enumerate(components):
            if not isinstance(comp, dict):
                continue
            accessibility = comp.get("accessibility")
            if accessibility is None:
                continue
            base = f"/{msg_idx}/updateComponents/components/{comp_idx}/accessibility"
            if not isinstance(accessibility, dict):
                reasons.append(
                    A2uiRejectReason(
                        validator="accessible_name",
                        json_pointer=base,
                        message="accessibility must be an object with a label/description.",
                    )
                )
                continue
            label = accessibility.get("label")
            description = accessibility.get("description")
            has_name = (isinstance(label, str) and label.strip()) or (
                isinstance(description, str) and description.strip()
            )
            if not has_name:
                reasons.append(
                    A2uiRejectReason(
                        validator="accessible_name",
                        json_pointer=base,
                        message=(
                            "A declared accessibility block must carry a non-empty "
                            "'label' or 'description' (accessible name)."
                        ),
                    )
                )
    return reasons


def _data_model_rows(messages: list[Any]) -> list[tuple[int, list[Any]]]:
    """Extract ``(message_index, /tokens rows)`` from each ``updateDataModel`` msg.

    Args:
        messages: The A2UI message list.

    Returns:
        ``(index, rows)`` for each ``updateDataModel`` whose ``value.tokens`` is a
        list; other shapes are skipped (contrast is honest no-op when no rows).
    """
    out: list[tuple[int, list[Any]]] = []
    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            continue
        update = msg.get("updateDataModel")
        if not isinstance(update, dict):
            continue
        value = update.get("value")
        if not isinstance(value, dict):
            continue
        rows = value.get("tokens")
        if isinstance(rows, list):
            out.append((idx, rows))
    return out


def _infer_contrast_pairs(
    rows: list[Any],
) -> list[tuple[str, str, tuple[int, int, int], tuple[int, int, int]]]:
    """Infer foreground/background color pairs from flat ``/tokens`` rows.

    A row is ``{"path": <name>, "value": <display string>}``. A foreground row
    (path ending in a foreground suffix) is paired with the background row sharing
    its prefix (foreground-suffix stripped, then a background suffix appended), when
    both values parse to colors.

    Args:
        rows: The ``/tokens`` row list.

    Returns:
        ``(fg_path, bg_path, fg_rgb, bg_rgb)`` for each inferable, color-parseable
        pair (possibly empty — honest no-op scope).
    """
    by_path: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = row.get("path")
        value = row.get("value")
        if isinstance(path, str) and isinstance(value, str):
            by_path[path] = value

    pairs: list[tuple[str, str, tuple[int, int, int], tuple[int, int, int]]] = []
    for fg_path, fg_value in by_path.items():
        matched_fg_suffix = next((s for s in _FOREGROUND_SUFFIXES if fg_path.endswith(s)), None)
        if matched_fg_suffix is None:
            continue
        fg_rgb = _parse_color(fg_value)
        if fg_rgb is None:
            continue
        prefix = fg_path[: -len(matched_fg_suffix)]
        for bg_suffix in _BACKGROUND_SUFFIXES:
            bg_path = f"{prefix}{bg_suffix}"
            bg_value = by_path.get(bg_path)
            if bg_value is None:
                continue
            bg_rgb = _parse_color(bg_value)
            if bg_rgb is None:
                continue
            pairs.append((fg_path, bg_path, fg_rgb, bg_rgb))
            break
    return pairs


def _validate_token_contrast(
    messages: list[Any],
    design_tokens: dict[str, Any],
) -> list[A2uiRejectReason]:
    """Validate AA contrast on inferable fg/bg token pairs in the data model.

    Reuses the WCAG primitives from :mod:`atelier.gates.contrast`. Honest scope:
    where no fg/bg pair can be inferred this is a no-op PASS (cascade contrast is
    axe-core's job). Any inferable pair below :data:`_AA_NORMAL_RATIO` (4.5:1) →
    REJECT.

    Args:
        messages: The A2UI message list (the ``/tokens`` rows are read from the
            ``updateDataModel`` message — this is the surface that renders).
        design_tokens: The resolved design-token map (reserved for future
            pair-inference enrichment; the rendered ``/tokens`` rows are the
            authoritative source today). Logged for traceability.

    Returns:
        A list of :class:`A2uiRejectReason` (empty iff every inferable pair clears
        AA, or no pairs are inferable).
    """
    reasons: list[A2uiRejectReason] = []
    for msg_idx, rows in _data_model_rows(messages):
        pairs = _infer_contrast_pairs(rows)
        if not pairs:
            logger.debug(
                "atelier.a2ui.gate.contrast.no_pairs",
                extra={
                    "message_index": msg_idx,
                    "row_count": len(rows),
                    "design_token_count": len(design_tokens),
                },
            )
            continue
        for fg_path, bg_path, fg_rgb, bg_rgb in pairs:
            ratio = _contrast_ratio(fg_rgb, bg_rgb)
            if ratio < _AA_NORMAL_RATIO:
                reasons.append(
                    A2uiRejectReason(
                        validator="contrast",
                        json_pointer=f"/{msg_idx}/updateDataModel/value/tokens",
                        message=(
                            f"Token pair {fg_path!r} on {bg_path!r} has contrast "
                            f"{ratio:.2f}:1 < AA {_AA_NORMAL_RATIO:.1f}:1."
                        ),
                    )
                )
    return reasons


def _build_governance_messages(
    surface_id: str,
    reasons: list[A2uiRejectReason],
) -> list[dict[str, Any]]:
    """Build the custom governance event list emitted INSTEAD of a rejected surface.

    The event shape (ADR-0024 §2) carries a machine-readable VALIDATION_FAILED
    diagnostic per reason (the A2UI failure-report SHAPE, repurposed server-side —
    see the module NOTE).

    Args:
        surface_id: The rejected surface's id.
        reasons: The structured REJECT reasons.

    Returns:
        A one-element list holding the custom governance event.
    """
    errors = [
        {
            "code": "VALIDATION_FAILED",
            "surfaceId": surface_id,
            "path": reason.json_pointer,
            "message": reason.message,
        }
        for reason in reasons
    ]
    return [
        {
            "version": _A2UI_WIRE_VERSION,
            "custom": {
                "surfaceId": surface_id,
                "name": _GOVERNANCE_EVENT_NAME,
                "payload": {
                    "decision": "REJECT",
                    "gate": _GATE_NAME,
                    "errors": errors,
                },
            },
        }
    ]


def gate_a2ui_surface(
    messages: list[dict[str, Any]],
    *,
    design_tokens: dict[str, Any],
    surface_id: str,
    allowed_components: Mapping[str, frozenset[str]] | None = None,
) -> A2uiGateResult:
    """Fail-closed gate over an A2UI surface (the cross-track G2 entry point).

    Runs the four deterministic validators (envelope, catalog, accessible_name,
    contrast). On a clean pass returns ``A2uiGateResult(passed=True)`` with empty
    ``reasons`` / ``governance_messages`` — the caller emits the surface unchanged
    (identity transform). On any failure returns ``passed=False`` carrying the
    structured ``reasons`` and the custom ``governance_messages`` the caller emits
    instead of the surface (the caller also blanks ``a2ui_payload`` so the frontend
    fail-soft fallback engages).

    Pure: no I/O, no LLM, no network, no browser. The input ``messages`` list is
    never mutated.

    Args:
        messages: The ordered A2UI server-to-client message list to gate.
        design_tokens: The resolved design-token map (used by the contrast
            validator for traceability; the rendered ``/tokens`` rows are the
            authoritative contrast source).
        surface_id: The surface identifier (echoed into governance events).
        allowed_components: The catalog allowlist
            (``componentType -> required-prop names``). Defaults to the Atelier
            catalog :data:`atelier.a2ui.catalog.ALLOWED_COMPONENTS`.

    Returns:
        An :class:`A2uiGateResult`.
    """
    allowed = allowed_components if allowed_components is not None else ALLOWED_COMPONENTS

    reasons: list[A2uiRejectReason] = []
    reasons.extend(_validate_envelope(messages))
    reasons.extend(_validate_catalog(messages, allowed))
    reasons.extend(_validate_accessible_names(messages))
    reasons.extend(_validate_token_contrast(messages, design_tokens))

    if not reasons:
        logger.debug(
            "atelier.a2ui.gate.passed",
            extra={"surface_id": surface_id, "message_count": len(messages)},
        )
        return A2uiGateResult(passed=True, reasons=[], governance_messages=[])

    logger.warning(
        "atelier.a2ui.gate.rejected",
        extra={
            "surface_id": surface_id,
            "reason_count": len(reasons),
            "validators": sorted({r.validator for r in reasons}),
            "first_json_pointer": reasons[0].json_pointer,
        },
    )
    return A2uiGateResult(
        passed=False,
        reasons=reasons,
        governance_messages=_build_governance_messages(surface_id, reasons),
    )


__all__ = [
    "A2uiGateResult",
    "A2uiRejectReason",
    "gate_a2ui_surface",
]
