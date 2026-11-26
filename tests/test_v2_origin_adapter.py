import asyncio
import json

import pytest

from remnant.api.app import create_protected_origin_app
from remnant.auth.policy import AuthorizationPolicy
from remnant.origin.fastapi import FastAPIOriginAdapter
from remnant.origin.protocols import OriginAdapter


def call(adapter, resource_id, principal_id):
    return asyncio.run(
        adapter.get_protected(resource_id, principal_id=principal_id)
    )


@pytest.fixture
def setup_origin():
    policy = AuthorizationPolicy()
    app = create_protected_origin_app(policy)
    return policy, FastAPIOriginAdapter(app)


def test_fastapi_adapter_satisfies_origin_contract(setup_origin):
    _, adapter = setup_origin
    assert isinstance(adapter, OriginAdapter)


def test_origin_adapter_returns_protected_content_after_grant(setup_origin):
    policy, adapter = setup_origin
    policy.grant("alice", "document-1")

    response = call(adapter, "document-1", "alice")

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["resource_id"] == "document-1"
    assert payload["canary"] == "remnant-canary-document-1-7b91c2e4"


def test_origin_adapter_preserves_independent_denial(setup_origin):
    _, adapter = setup_origin

    response = call(adapter, "document-1", "mallory")

    assert response.status_code == 403
    assert b"remnant-canary-document-1-7b91c2e4" not in response.body


def test_revocation_is_observed_by_origin_adapter(setup_origin):
    policy, adapter = setup_origin
    policy.grant("alice", "document-1")
    assert call(adapter, "document-1", "alice").status_code == 200

    policy.revoke("alice", "document-1")

    response = call(adapter, "document-1", "alice")
    assert response.status_code == 403


def test_origin_adapter_returns_not_found_for_unknown_resource(setup_origin):
    policy, adapter = setup_origin
    policy.grant("alice", "unknown-resource")

    response = call(adapter, "unknown-resource", "alice")

    assert response.status_code == 404


@pytest.mark.parametrize(
    "resource_id,principal_id",
    [("", "alice"), ("document-1", ""), (" ", "alice")],
)
def test_origin_adapter_rejects_empty_identity_inputs(setup_origin, resource_id, principal_id):
    _, adapter = setup_origin
    with pytest.raises(ValueError):
        call(adapter, resource_id, principal_id)
