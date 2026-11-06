"""REST scopes must be issuable for the local bootstrap key."""

from __future__ import annotations

from app.modules.identity.api_key import ALLOWED_SCOPES, ISSUABLE_SCOPES, REST_SCOPES


def test_rest_and_admin_scopes_are_issuable() -> None:
    assert {
        "projects:read",
        "projects:write",
        "datasets:read",
        "datasets:write",
        "datasources:read",
        "datasources:write",
        "runs:read",
        "runs:write",
        "evaluators:read",
        "evaluators:write",
        "gate:read",
        "reports:read",
        "badcases:read",
        "functional:read",
        "functional:write",
        "admin:read",
        "admin:write",
        "platform:admin",
    } <= ISSUABLE_SCOPES
    assert REST_SCOPES <= ISSUABLE_SCOPES
    assert REST_SCOPES.isdisjoint(ALLOWED_SCOPES)
