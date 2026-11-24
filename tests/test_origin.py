import asyncio

import httpx
import pytest

import remnant.api.app as app_module
from remnant.auth.policy import AuthorizationPolicy


@pytest.fixture
def policy(monkeypatch):
    current_policy = AuthorizationPolicy()
    monkeypatch.setattr(
        app_module,
        "authorization_policy",
        current_policy,
        raising=False,
    )
    return current_policy


def request(method, path):
    async def send_request():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path)

    return asyncio.run(send_request())


def test_authorized_principal_gets_resource_with_stable_canary(policy):
    policy.grant("alice", "document-1")

    first_response = request(
        "GET",
        "/protected/document-1?principal_id=alice",
    )
    second_response = request(
        "GET",
        "/protected/document-1?principal_id=alice",
    )

    expected = {
        "resource_id": "document-1",
        "content": "Confidential project notes for document one.",
        "canary": "remnant-canary-document-1-7b91c2e4",
    }
    assert first_response.status_code == 200
    assert first_response.json() == expected
    assert second_response.json()["canary"] == expected["canary"]


def test_unauthorized_response_does_not_expose_resource_or_canary(policy):
    response = request(
        "GET",
        "/protected/document-1?principal_id=mallory",
    )

    assert response.status_code == 403
    assert "Confidential project notes for document one." not in response.text
    assert "remnant-canary-document-1-7b91c2e4" not in response.text


def test_revoked_principal_is_denied_on_next_request(policy):
    policy.grant("alice", "document-1")
    assert request(
        "GET",
        "/protected/document-1?principal_id=alice",
    ).status_code == 200

    policy.revoke("alice", "document-1")
    response = request(
        "GET",
        "/protected/document-1?principal_id=alice",
    )

    assert response.status_code == 403
    assert "remnant-canary-document-1-7b91c2e4" not in response.text


def test_revoking_one_principal_preserves_another_principals_access(policy):
    policy.grant("alice", "document-1")
    policy.grant("bob", "document-1")
    policy.revoke("alice", "document-1")

    alice_response = request(
        "GET",
        "/protected/document-1?principal_id=alice",
    )
    bob_response = request(
        "GET",
        "/protected/document-1?principal_id=bob",
    )

    assert alice_response.status_code == 403
    assert bob_response.status_code == 200
    assert bob_response.json()["canary"] == "remnant-canary-document-1-7b91c2e4"


def test_grant_for_one_resource_does_not_allow_another(policy):
    policy.grant("alice", "document-1")

    response = request(
        "GET",
        "/protected/document-2?principal_id=alice",
    )

    assert response.status_code == 403
    assert "remnant-canary-document-2-d45a08f3" not in response.text


def test_missing_principal_is_rejected_without_resource_data(policy):
    response = request("GET", "/protected/document-1")

    assert response.status_code == 422
    assert "Confidential project notes for document one." not in response.text
    assert "remnant-canary-document-1-7b91c2e4" not in response.text
