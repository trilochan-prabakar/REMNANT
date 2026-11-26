import pytest

from remnant.auth import (
    AccountStatus, IdentityRegistry, PermissionStore, PolicyEngine,
    Principal, Resource, ResourceRegistry, Role, Tenant, TenantRegistry,
)


@pytest.fixture
def world():
    tenants = TenantRegistry()
    tenants.register(Tenant("tenant-a"))
    tenants.register(Tenant("tenant-b"))
    identities = IdentityRegistry()
    identities.register(Principal("alice", Role.USER, tenant_id="tenant-a"))
    identities.register(Principal("bob", Role.USER, tenant_id="tenant-a"))
    identities.register(Principal("mallory", Role.USER, tenant_id="tenant-b"))
    identities.register(Principal("admin-a", Role.TENANT_ADMIN, tenant_id="tenant-a"))
    resources = ResourceRegistry()
    resources.register(Resource("doc-a", "tenant-a", "alice"))
    resources.register(Resource("doc-b", "tenant-b", "mallory"))
    permissions = PermissionStore()
    return PolicyEngine(identities, resources, permissions, tenants), identities, resources, permissions, tenants


def test_owner_can_read_own_resource_but_not_manage(world):
    engine, *_ = world
    assert engine.evaluate("alice", "doc-a", "read").reason == "resource_owner"
    decision = engine.evaluate("alice", "doc-a", "manage")
    assert decision.allowed is False
    assert decision.reason == "no_active_permission"


def test_tenant_boundary_is_checked_before_admin_role(world):
    engine, *_ = world
    decision = engine.evaluate("admin-a", "doc-b", "read")
    assert decision.allowed is False
    assert decision.reason == "tenant_boundary"


def test_tenant_admin_is_scoped_to_own_tenant(world):
    engine, *_ = world
    decision = engine.evaluate("admin-a", "doc-a", "manage")
    assert decision.allowed is True
    assert decision.reason == "tenant_administrator"


def test_explicit_deny_overrides_resource_ownership(world):
    engine, _, _, permissions, _ = world
    permissions.deny("alice", "doc-a", "read")
    decision = engine.evaluate("alice", "doc-a", "read")
    assert decision.allowed is False
    assert decision.reason == "explicit_denial"


def test_explicit_grant_allows_non_owner(world):
    engine, _, _, permissions, _ = world
    permissions.grant("bob", "doc-a", "read")
    decision = engine.evaluate("bob", "doc-a", "read")
    assert decision.allowed is True
    assert decision.reason == "explicit_grant"


@pytest.mark.parametrize(
    ("status", "reason"),
    [(AccountStatus.SUSPENDED, "identity_suspended"),
     (AccountStatus.REMOVED, "identity_removed")],
)
def test_inactive_identity_is_denied(world, status, reason):
    engine, identities, *_ = world
    if status is AccountStatus.SUSPENDED:
        identities.suspend("alice")
    else:
        identities.remove("alice")
    decision = engine.evaluate("alice", "doc-a")
    assert decision.allowed is False
    assert decision.reason == reason


def test_inactive_tenant_is_denied(world):
    engine, _, _, _, tenants = world
    tenants.set_active("tenant-a", False)
    decision = engine.evaluate("alice", "doc-a")
    assert decision.allowed is False
    assert decision.reason == "tenant_inactive"


def test_unknown_identity_and_resource_fail_closed(world):
    engine, *_ = world
    assert engine.evaluate("ghost", "doc-a").reason == "unknown_principal"
    assert engine.evaluate("alice", "missing").reason == "unknown_resource"


def test_permission_policy_version_increments_only_on_changes(world):
    engine, _, _, permissions, _ = world
    initial = engine.version
    permissions.grant("bob", "doc-a")
    assert engine.version == initial + 1
    permissions.grant("bob", "doc-a")
    assert engine.version == initial + 1
    permissions.revoke("bob", "doc-a")
    assert engine.version == initial + 2


def test_role_updates_and_removed_identity_cannot_be_reactivated(world):
    _, identities, *_ = world
    identities.set_roles("bob", (Role.TENANT_ADMIN,))
    assert Role.TENANT_ADMIN in identities.get("bob").effective_roles
    identities.remove("bob")
    with pytest.raises(ValueError, match="removed identities"):
        identities.reactivate("bob")


def test_resource_registry_rejects_duplicate_ids(world):
    _, _, resources, *_ = world
    with pytest.raises(ValueError, match="already exists"):
        resources.register(Resource("doc-a", "tenant-a", "alice"))
