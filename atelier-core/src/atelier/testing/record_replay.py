"""Record/replay determinism harness (PRD v2.2 AT-003).

Two responsibilities, both CI/test-only:

1. **Canonicalization** -- :func:`canonicalize_trajectory` normalizes the
   inherently-nondeterministic fields of a pipeline result (uuids, ids,
   timestamps) to fixed sentinels and sorts keys, so two runs of the same
   offline pipeline serialize byte-for-byte identically. This is what makes
   "3x -> byte-identical canonical trajectory (sha256 equal)" checkable.

2. **Live-call guard** -- :class:`LiveCallGuard` patches the real model/tool
   client entrypoints so that any live network call during a hermetic run is
   counted (and raises). A passing hermetic run asserts ``guard.live_calls == 0``.

The record/replay *cassette* (capturing real tool/model responses by request
hash via an ADK ``before_model_callback`` so a future run can serve them
offline) builds on :func:`request_hash` below; the deterministic offline
pipeline used by ``make verify`` runs against faked/heuristic model surfaces and
canonicalization, so no live responses are needed to prove determinism.
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import re
import uuid as _uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

# --- canonicalization --------------------------------------------------------

CANON_UUID = "00000000-0000-0000-0000-000000000000"
CANON_ID = "CANON-ID"
CANON_TS = "CANON-TS"

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
# Field names whose VALUES are run-specific identifiers (not uuid-shaped).
_ID_FIELDS = frozenset({"session_id", "run_id", "insert_id", "campaign_id", "task_id", "id"})
# Field names whose VALUES are timestamps (ISO-8601 strings or epoch numbers).
_TS_FIELDS = frozenset(
    {
        "ts",
        "timestamp",
        "started_at",
        "ended_at",
        "completed_at",
        "approved_at",
        "created_at",
        "updated_at",
        "signed_off_at",
    }
)


def _canon_value(key: str | None, value: Any) -> Any:  # noqa: PLR0911 - flat normalization dispatch
    """Normalize a single value by field name and shape."""
    if isinstance(value, dict):
        return {k: _canon_value(k, v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_canon_value(key, v) for v in value]
    # Raw uuid / datetime objects collapse to their sentinels before serialization.
    if isinstance(value, _uuid.UUID):
        return CANON_UUID
    if isinstance(value, (datetime.datetime, datetime.date)):
        return CANON_TS
    if key in _TS_FIELDS and value is not None:
        return CANON_TS
    if key in _ID_FIELDS and isinstance(value, str):
        return CANON_UUID if _UUID_RE.match(value) else CANON_ID
    if isinstance(value, str) and _UUID_RE.match(value):
        return CANON_UUID
    return value


def canonicalize_trajectory(obj: Any) -> str:
    """Return a deterministic, byte-stable JSON string for ``obj``.

    uuids -> ``CANON_UUID``; ``*_id`` run identifiers -> sentinel; timestamp
    fields -> ``CANON_TS``; dict keys sorted; compact stable separators. Two
    runs of the same offline pipeline canonicalize to identical bytes.
    """
    canon = _canon_value(None, obj)
    return json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def trajectory_sha256(obj: Any) -> str:
    """sha256 of the canonical trajectory -- the determinism fingerprint."""
    return hashlib.sha256(canonicalize_trajectory(obj).encode("utf-8")).hexdigest()


def request_hash(payload: Any) -> str:
    """Stable hash of a model/tool request, used as the cassette key."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# --- live-call guard ---------------------------------------------------------


class LiveCallError(RuntimeError):
    """Raised when a hermetic run attempts a real model/tool network call."""


class LiveCallGuard:
    """Counts (and forbids) live model/tool calls during a hermetic run.

    Patches the real client entrypoints so a hermetic run that accidentally
    reaches the network is caught. A passing offline run leaves ``live_calls``
    at 0 because every model surface is faked/heuristic.
    """

    # Fully-qualified entrypoints that perform real network I/O (not the
    # config-only constructors, which the default runner builds offline).
    _TARGETS = (
        "atelier.nodes.llm_judge.VertexAIJudgeClient.generate",
        "atelier.intake.web_research._get_genai_client",
    )

    def __init__(self) -> None:
        self.live_calls = 0
        self._patchers: list[Any] = []

    def _trip(self, *_args: Any, **_kwargs: Any) -> Any:
        self.live_calls += 1
        raise LiveCallError(
            "hermetic run attempted a live model/tool call (AT-003); "
            "all model surfaces must be faked/replayed offline"
        )

    def __enter__(self) -> LiveCallGuard:
        for target in self._TARGETS:
            with contextlib.suppress(AttributeError, ModuleNotFoundError, ImportError):
                p = patch(target, side_effect=self._trip)
                p.start()
                self._patchers.append(p)
        return self

    def __exit__(self, *_exc: Any) -> None:
        for p in self._patchers:
            with contextlib.suppress(RuntimeError):
                p.stop()
        self._patchers.clear()


@contextlib.contextmanager
def hermetic() -> Iterator[LiveCallGuard]:
    """Context manager yielding a :class:`LiveCallGuard` for an offline run."""
    with LiveCallGuard() as guard:
        yield guard
