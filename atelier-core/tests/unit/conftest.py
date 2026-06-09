"""Shared pytest configuration for the unit suite.

Pin a fake GCP project before any test module is imported. Tests that build the
real ADK agent graph offline (``test_agent_engine_deploy``) construct model
clients that resolve a project from the environment; CI has no Application
Default Credentials, so without a project they raise ``GoogleAuthError: Unable
to find your project``. The value is never used for a network call — the offline
construction never invokes ``vertexai.agent_engines.create()``. ``setdefault``
preserves a real project when one is configured (local development).
"""

from __future__ import annotations

import os

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "atelier-test")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "false")
