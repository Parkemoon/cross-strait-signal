"""Admin authentication for write endpoints.

When the ADMIN_TOKEN environment variable is set, all routes that mutate state
must include an ``X-Admin-Token`` header matching it. When the variable is
unset or empty, the dependency is a no-op — this keeps local development and
existing production deployments working until the token is rolled out.

Production rollout:
  1. Generate a token: ``python -c 'import secrets; print(secrets.token_urlsafe(32))'``
  2. Add ``ADMIN_TOKEN=...`` to the server ``.env`` and to the admin frontend
     build env (``REACT_APP_ADMIN_TOKEN=...``).
  3. Restart the API service and redeploy the admin build.
  4. The public read-only build does not need the token because it only issues
     GET requests, and nginx blocks writes there anyway.
"""
import hmac
import os
from fastapi import Header, HTTPException, status


def _admin_token() -> str:
    return os.environ.get("ADMIN_TOKEN", "").strip()


def is_admin(x_admin_token: str = Header(default="")) -> bool:
    """FastAPI dependency for read routes with an admin-only superset.

    True when the caller presented a valid ``X-Admin-Token`` (or when no token
    is configured — the legacy nginx-only mode where every caller is trusted).
    Unlike ``require_admin`` this never raises, so public callers simply get
    the non-admin view.
    """
    expected = _admin_token()
    if not expected:
        return True
    return hmac.compare_digest(x_admin_token, expected)


def require_admin(x_admin_token: str = Header(default="")) -> None:
    """FastAPI dependency. Validates ``X-Admin-Token`` when ADMIN_TOKEN is set.

    Use as ``Depends(require_admin)`` on any route that writes.
    """
    expected = _admin_token()
    if not expected:
        # Token not configured — fall back to the legacy nginx-only behaviour.
        return
    if not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Admin-Token",
        )
