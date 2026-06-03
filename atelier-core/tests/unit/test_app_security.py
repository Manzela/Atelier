"""API hardening regressions: transport-security headers, OpenAPI exposure,
and operator-config validation (audit S4 / S9 / S7).

  - S4: every response carries HSTS + X-Content-Type-Options on the direct
    Cloud Run host, not only behind the Cloudflare edge.
  - S9: the raw OpenAPI schema (/openapi.json) and interactive docs are
    development-only — a paid, authenticated production API must not publish
    its full route/parameter surface. FastAPI serves /openapi.json by default
    even when docs_url is None, so it is gated explicitly.
  - S7: ATELIER_JUDGE_MODE is operator-set config; a non-canonical value must
    fail loud at STARTUP (validate_judge_mode_env), not 500 every request.
"""

from __future__ import annotations

import pytest
from atelier.api.app import create_app
from atelier.nodes.llm_judge import (
    ATELIER_JUDGE_MODE_ENV,
    DEFAULT_JUDGE_MODE,
    validate_judge_mode_env,
)
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ──────────────────────────────────────────────────────────────────────
# S4 — transport-security headers on every response
# ──────────────────────────────────────────────────────────────────────


class TestSecurityHeaders:
    @pytest.mark.unit
    @pytest.mark.anyio
    async def test_hsts_present(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        hsts = resp.headers.get("Strict-Transport-Security", "")
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts

    @pytest.mark.unit
    @pytest.mark.anyio
    async def test_nosniff_present(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    @pytest.mark.unit
    @pytest.mark.anyio
    async def test_timing_header_still_present(self, client: AsyncClient) -> None:
        # The headers were added to the existing timing middleware; it must still time.
        resp = await client.get("/health")
        assert "X-Process-Time" in resp.headers


# ──────────────────────────────────────────────────────────────────────
# S9 — OpenAPI schema / docs are development-only
# ──────────────────────────────────────────────────────────────────────


class TestOpenApiExposure:
    @pytest.mark.unit
    @pytest.mark.anyio
    async def test_openapi_json_blocked_in_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATELIER_ENV", "production")
        prod_app = create_app()
        transport = ASGITransport(app=prod_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            assert (await c.get("/openapi.json")).status_code == 404
            assert (await c.get("/docs")).status_code == 404

    @pytest.mark.unit
    @pytest.mark.anyio
    async def test_openapi_json_available_in_development(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATELIER_ENV", "development")
        dev_app = create_app()
        transport = ASGITransport(app=dev_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            assert (await c.get("/openapi.json")).status_code == 200


# ──────────────────────────────────────────────────────────────────────
# S7 — ATELIER_JUDGE_MODE startup validation (fail-loud, fail-early)
# ──────────────────────────────────────────────────────────────────────


class TestJudgeModeStartupValidation:
    @pytest.mark.unit
    def test_unset_returns_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(ATELIER_JUDGE_MODE_ENV, raising=False)
        assert validate_judge_mode_env() == DEFAULT_JUDGE_MODE

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("llm", "llm"), ("  LLM ", "llm"), ("Hybrid", "hybrid"), ("HEURISTIC", "heuristic")],
    )
    def test_normalizes_whitespace_and_case(
        self, monkeypatch: pytest.MonkeyPatch, raw: str, expected: str
    ) -> None:
        monkeypatch.setenv(ATELIER_JUDGE_MODE_ENV, raw)
        assert validate_judge_mode_env() == expected

    @pytest.mark.unit
    def test_blank_value_returns_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ATELIER_JUDGE_MODE_ENV, "   ")
        assert validate_judge_mode_env() == DEFAULT_JUDGE_MODE

    @pytest.mark.unit
    def test_garbage_value_raises_loud(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ATELIER_JUDGE_MODE_ENV, "huristic")
        with pytest.raises(ValueError, match="not a valid judge mode"):
            validate_judge_mode_env()
