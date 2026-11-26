"""End-to-end tests for the separately selectable tenant-aware V2 path."""

import hashlib
import json
from uuid import uuid4

from remnant.api.v2 import create_v2_protected_origin_app
from remnant.auth.adapter import PolicyEngineAdapter
from remnant.auth.identities import IdentityRegistry
from remnant.auth.models import AccountStatus, Principal, Resource, Role
from remnant.auth.ownership import ResourceRegistry
from remnant.auth.permissions import PermissionStore
from remnant.auth.policy import PolicyEngine
from remnant.auth.tenancy import Tenant, TenantRegistry
from remnant.cache.manager import RedisCacheManager
from remnant.engine.experiment import CacheReplayExperiment
from remnant.reporting import ReportGenerator
from remnant.storage import SQLiteEvidenceStore


class MemoryRedis:
    def __init__(self):
        self.values = {}

    def set(self, key, value, *, ex):
        self.values[key] = value
        return True

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        return int(self.values.pop(key, None) is not None)


def build_engine():
    identities = IdentityRegistry()
    identities.register(Principal("alice", Role.USER, tenant_id="tenant-a"))
    identities.register(Principal("bob", Role.USER, tenant_id="tenant-b"))
    identities.register(Principal("tenant-admin-a", Role.TENANT_ADMIN, tenant_id="tenant-a"))
    identities.register(Principal("owner-a", Role.USER, tenant_id="tenant-a"))
    resources = ResourceRegistry()
    resources.register(Resource("document-1", "tenant-a", "owner-a"))
    resources.register(Resource("document-2", "tenant-b", "owner-b"))
    tenants = TenantRegistry()
    tenants.register(Tenant("tenant-a"))
    tenants.register(Tenant("tenant-b"))
    permissions = PermissionStore()
    return PolicyEngine(identities, resources, permissions, tenants), identities, resources, tenants, permissions


def build_experiment(engine):
    adapter = PolicyEngineAdapter(engine)
    origin = create_v2_protected_origin_app(adapter)
    cache = RedisCacheManager(
        client=MemoryRedis(), key_prefix=f"remnant:v2-tenant:{uuid4().hex}:"
    )
    return CacheReplayExperiment(cache=cache, policy=adapter, origin_app=origin)


def test_v2_tenant_path_uses_registry_tenant_in_cache_key_and_metadata(tmp_path):
    engine, *_ = build_engine()
    experiment = build_experiment(engine)

    result = experiment.run("alice", "document-1")

    assert result.tenant_id == "tenant-a"
    assert result.initial_authorization_status == 200
    assert result.permission_revoked is True
    assert result.origin_status_after_revocation == 403
    assert result.cache_primed is True
    assert result.finding_status == "CONFIRMED"
    assert result.analysis_evidence.cache_prime_metadata.tenant_id == "tenant-a"
    assert result.analysis_evidence.replay_metadata.tenant_id == "tenant-a"
    assert result.analysis_evidence.replay_metadata.valid is True

    store = SQLiteEvidenceStore(tmp_path / "tenant-evidence.sqlite3")
    store.save_experiment(result)
    saved = store.get_experiment(result.experiment_id)
    report = json.loads(
        ReportGenerator(store, tmp_path / "reports")
        .generate_json(result.experiment_id)
        .read_text()
    )
    analysis = json.loads(saved["analysis"]["analysis_json"])
    assert analysis["replay_metadata"]["tenant_id"] == "tenant-a"
    assert report["analysis"]["replay_metadata"]["tenant_id"] == "tenant-a"
    assert "tenant-a" not in report["experiment"].get("cache_key", "")


def test_v2_origin_serves_resources_registered_outside_v1_sample_catalogue():
    engine, _, resources, _, _ = build_engine()
    resources.register(Resource("customer-export-42", "tenant-a", "owner-a"))
    experiment = build_experiment(engine)

    result = experiment.run("alice", "customer-export-42")

    assert result.initial_authorization_status == 200
    assert result.cache_primed is True
    assert result.permission_revoked is True
    assert result.origin_status_after_revocation == 403
    assert result.oracle_cache_hit is True
    assert result.oracle_canary_matches is True
    assert result.finding_status == "CONFIRMED"
    assert result.cached_canary == (
        f"remnant-canary-customer-export-42-"
        f"{hashlib.sha256(b'customer-export-42').hexdigest()[:8]}"
    )


def test_tenant_a_cannot_prime_or_replay_tenant_b_resource():
    engine, *_ = build_engine()
    experiment = build_experiment(engine)

    result = experiment.run("alice", "document-2")

    assert result.tenant_id == "tenant-a"
    assert result.initial_authorization_status == 403
    assert result.cache_primed is False
    assert result.origin_status_after_revocation == 403
    assert result.cache_observation_status == "MISS"
    assert result.finding_status == "NOT_FOUND"
    assert result.oracle_cache_hit is False


def test_tenant_admin_role_does_not_cross_tenant_boundary():
    engine, *_ = build_engine()
    decision = engine.evaluate("tenant-admin-a", "document-2")

    assert decision.allowed is False
    assert decision.reason == "tenant_boundary"


def test_explicit_deny_precedes_owner_and_tenant_admin_grants():
    engine, *_ = build_engine()
    engine.permissions.deny("owner-a", "document-1", "read")

    decision = engine.evaluate("owner-a", "document-1")
    assert decision.allowed is False
    assert decision.reason == "explicit_denial"


def test_suspended_removed_and_inactive_tenant_identities_fail_closed():
    engine, identities, _, tenants, _ = build_engine()

    identities.suspend("alice")
    assert engine.evaluate("alice", "document-1").reason == "identity_suspended"
    identities.reactivate("alice")
    identities.remove("alice")
    assert engine.evaluate("alice", "document-1").reason == "identity_removed"

    tenants.set_active("tenant-b", False)
    assert engine.evaluate("bob", "document-2").reason == "tenant_inactive"


def test_unknown_identity_resource_and_tenant_fail_closed():
    engine, identities, resources, tenants, _ = build_engine()

    assert engine.evaluate("nobody", "document-1").reason == "unknown_principal"
    assert engine.evaluate("alice", "missing-resource").reason == "unknown_resource"

    identities.register(Principal("orphan", Role.USER, tenant_id="missing-tenant"))
    assert engine.evaluate("orphan", "document-1").reason == "unknown_tenant"
