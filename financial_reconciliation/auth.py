"""Minimal admin authentication for the web app.

Credentials live here (overridable by environment variables). Change them for
your deployment:

    FINRECON_ADMIN_USER      (default "admin")
    FINRECON_ADMIN_PASSWORD  (default "change-me-please")
    FINRECON_ADMIN_TOKEN     (optional static token; otherwise login issues one)

IMPORTANT: this is a minimal gate, not production authentication. It keeps the
admin actions off the public surface and verifies credentials server-side, but
a serious deployment should use Dataiku's built-in user auth / SSO and its
permissions model instead of credentials stored in code or environment.
"""
from __future__ import annotations

import os
import secrets

ADMIN_USERNAME = os.environ.get("FINRECON_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("FINRECON_ADMIN_PASSWORD", "change-me-please")

_ISSUED: set = set()


def login(username: str, password: str) -> str | None:
    """Verify credentials; on success return a session token, else None."""
    if not username or not password:
        return None
    ok_user = secrets.compare_digest(str(username), ADMIN_USERNAME)
    ok_pass = secrets.compare_digest(str(password), ADMIN_PASSWORD)
    if ok_user and ok_pass:
        token = secrets.token_urlsafe(24)
        _ISSUED.add(token)
        return token
    return None


def valid_token(token: str | None) -> bool:
    if not token:
        return False
    env = os.environ.get("FINRECON_ADMIN_TOKEN")
    if env and secrets.compare_digest(str(token), env):
        return True
    return token in _ISSUED
