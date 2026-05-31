"""R4 anchor re-injection (PRD v2.2 R4 / AT-005).

The immutable anchor (brief + tokens + research) is re-injected byte-identically
into the generator prompt every iteration, regardless of the mutating fixer
directive -- so accumulated rejected-variant history can never displace it.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from atelier.orchestrator.runner import _compose_anchor, _compose_generator_prompt


class _Brief:
    def model_dump_json(self) -> str:
        return '{"intent":"build a landing page","stack":"vanilla-html"}'


class _Ctx:
    design_tokens: ClassVar[dict[str, dict[str, str]]] = {
        "color": {"primary": "#0a0a0a"},
        "space": {"md": "16px"},
    }


class _Report:
    results: ClassVar[list[str]] = ["baymard: checkout best practice", "wcag 2.2 AA"]


@pytest.mark.unit
def test_anchor_is_deterministic() -> None:
    """Identical inputs -> byte-identical anchor (stable serialization)."""
    a1 = _compose_anchor(_Brief(), _Ctx(), _Report())
    a2 = _compose_anchor(_Brief(), _Ctx(), _Report())
    assert a1 == a2
    assert "build a landing page" in a1
    assert "#0a0a0a" in a1
    assert "wcag 2.2 AA" in a1


@pytest.mark.unit
def test_anchor_byte_identical_across_mutated_history() -> None:
    """Simulate the loop: the anchor prefix stays byte-identical as the fixer
    directive mutates each iteration, and the directive is REPLACED not accumulated."""
    anchor = _compose_anchor(_Brief(), _Ctx(), _Report())
    directives = ["", "raise the contrast", "use a 12-col grid", "tighten spacing"]
    prompts = [_compose_generator_prompt(anchor, "landing", d) for d in directives]

    # Every iteration re-injects the exact same anchor prefix.
    for prompt in prompts:
        assert prompt.startswith(anchor)
        assert prompt[: len(anchor)] == anchor

    # The directive is replaced, never accumulated: a later prompt carries only
    # its own directive, none of the earlier ones.
    assert "raise the contrast" not in prompts[2]
    assert "use a 12-col grid" not in prompts[3]
    assert "tighten spacing" in prompts[3]


@pytest.mark.unit
def test_anchor_handles_empty_tokens_and_research() -> None:
    """Missing tokens/research degrade to a stable, still-deterministic anchor."""

    class _EmptyCtx:
        design_tokens = None

    class _EmptyReport:
        results: ClassVar[list[str]] = []

    a1 = _compose_anchor(_Brief(), _EmptyCtx(), _EmptyReport())
    a2 = _compose_anchor(_Brief(), _EmptyCtx(), _EmptyReport())
    assert a1 == a2
    assert "build a landing page" in a1
