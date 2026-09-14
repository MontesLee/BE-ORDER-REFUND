"""Caller identity.

Identity is carried by the ``X-User-Id`` header.  That is deliberately minimal
-- the benchmark is about authorisation *semantics*, not about JWT plumbing.

Two rules matter and both are enforced in :mod:`app.service`:

1. Resource ownership.  A caller may only read/act on its own orders and
   after-sales.  Cross-tenant attempts are answered with ``404`` rather than
   ``403`` so that the response does not confirm whether the resource exists.
2. Role separation.  ``approve`` and ``execute`` are support-agent operations.
   A normal user can never approve their own request or push it straight to
   the refund channel.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from . import repository

USER_ROLE = "USER"
AGENT_ROLE = "AGENT"

HEADER_NAME = "X-User-Id"


class Unauthorized(Exception):
    """No usable caller identity."""


class Forbidden(Exception):
    """Caller is identified but not allowed to perform the operation."""


class NotFound(Exception):
    """Resource does not exist *or* is not visible to the caller."""


def resolve_user(user_id: Optional[int]) -> Dict[str, Any]:
    if user_id is None:
        raise Unauthorized(f"missing {HEADER_NAME} header")
    conn = repository.connect()
    try:
        user = repository.get_user(conn, int(user_id))
    finally:
        conn.close()
    if user is None:
        raise Unauthorized(f"unknown user id: {user_id}")
    return user


def require_agent(user: Dict[str, Any]) -> None:
    if user.get("role") != AGENT_ROLE:
        raise Forbidden("operation requires an after-sale agent role")


def is_agent(user: Dict[str, Any]) -> bool:
    return user.get("role") == AGENT_ROLE


def assert_can_view(user: Dict[str, Any], resource_user_id: int, what: str) -> None:
    """Ownership check shared by every read path."""
    if is_agent(user):
        return
    if int(resource_user_id) != int(user["id"]):
        # 404, not 403: do not leak the existence of another tenant's row.
        raise NotFound(f"{what} not found")
