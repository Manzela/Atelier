"""Pytest session setup shared across the unit + integration suites.

CI infra hardening (Python 3.11): ``google-genai``'s
``BaseApiClient.aclose()`` awaits ``self._async_httpx_client``, which is created
lazily on the FIRST async request. A client constructed but never used async —
e.g. when a fake ``BaseLlm`` intercepts the model call, or a grounded search is
stubbed — leaves that attribute unset, so ``aclose()`` raises ``AttributeError``
during anyio's event-loop teardown. The leaked client's teardown can then fail
an otherwise-passing async test (the exception surfaces on whichever test's
teardown the event loop happens to finalize it). This is a pre-existing genai
teardown quirk, unrelated to product code (real runs always issue the async
call, so the attribute exists). Tolerate exactly that teardown ``AttributeError``
so a never-used client cannot red a green test.
"""

from __future__ import annotations

from google.genai import _api_client as _genai_api_client

_ORIG_ACLOSE = _genai_api_client.BaseApiClient.aclose


async def _tolerant_aclose(self: _genai_api_client.BaseApiClient) -> None:
    try:
        await _ORIG_ACLOSE(self)
    except AttributeError as exc:
        # Only swallow the lazy-async-client teardown attrs; re-raise anything else.
        msg = str(exc)
        if "_async_httpx_client" not in msg and "_aiohttp_session" not in msg:
            raise


_genai_api_client.BaseApiClient.aclose = _tolerant_aclose  # type: ignore[method-assign]
