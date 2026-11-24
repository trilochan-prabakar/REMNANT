import pytest

from remnant.auth.models import Principal, Role
from remnant.auth.policy import AuthorizationPolicy


@pytest.fixture
def policy():
    return AuthorizationPolicy()


@pytest.fixture
def alice():
    return Principal("alice", Role.USER)


@pytest.fixture
def bob():
    return Principal("bob", Role.USER)


@pytest.fixture
def admin():
    return Principal("admin", Role.ADMIN)


def test_granted_user_can_access_resource(policy, alice):
    policy.grant("alice", "document-1")

    decision = policy.is_allowed(alice, "document-1")

    assert decision.allowed is True
    assert decision.reason == "explicit_grant"


def test_ungranted_user_is_denied(policy, bob):
    decision = policy.is_allowed(bob, "document-1")

    assert decision.allowed is False
    assert decision.reason == "no_active_grant"


def test_revoked_permission_is_denied(policy, alice):
    policy.grant("alice", "document-1")
    policy.revoke("alice", "document-1")

    decision = policy.is_allowed(alice, "document-1")

    assert decision.allowed is False
    assert decision.reason == "no_active_grant"


def test_revoking_alice_permission_preserves_bobs_access(policy, alice, bob):
    policy.grant("alice", "document-1")
    policy.grant("bob", "document-1")

    policy.revoke("alice", "document-1")

    alice_decision = policy.is_allowed(alice, "document-1")
    bob_decision = policy.is_allowed(bob, "document-1")

    assert alice_decision.allowed is False
    assert bob_decision.allowed is True


def test_permission_does_not_grant_access_to_another_resource(policy, alice):
    policy.grant("alice", "document-1")

    decision = policy.is_allowed(alice, "document-2")

    assert decision.allowed is False
    assert decision.reason == "no_active_grant"


def test_revoking_missing_permission_is_safe(policy, alice):
    policy.revoke("alice", "document-1")

    decision = policy.is_allowed(alice, "document-1")

    assert decision.allowed is False


def test_admin_can_access_resource(policy, admin):
    decision = policy.is_allowed(admin, "document-1")

    assert decision.allowed is True
    assert decision.reason == "administrator_access"


def test_empty_principal_id_is_rejected(policy):
    with pytest.raises(ValueError):
        policy.grant("", "document-1")


def test_empty_resource_id_is_rejected(policy, alice):
    with pytest.raises(ValueError):
        policy.is_allowed(alice, "")
