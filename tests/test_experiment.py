import json

import pytest

from remnant.auth.policy import AuthorizationPolicy
from remnant.auth.models import Principal, Role
import remnant.api.app as app_module
from remnant.api.app import create_protected_origin_app
from remnant.cache.manager import CacheStatus, RedisCacheManager
from remnant.engine.experiment import (
    CacheReplayExperiment,
    evaluate_finding,
)


class ExpiringRedis:
    def __init__(self):
        self.now = 0
        self.values = {}

    def set(self, key, value, *, ex):
        self.values[key] = (value, self.now + ex)

    def get(self, key):
        item = self.values.get(key)
        if item is None:
            return None
        value, expires_at = item
        if self.now >= expires_at:
            del self.values[key]
            return None
        return value


def build_experiment():
    policy = AuthorizationPolicy()
    redis = ExpiringRedis()
    cache = RedisCacheManager(client=redis, key_prefix="unit:")
    return CacheReplayExperiment(policy=policy, cache=cache), policy, redis


def test_authorized_cache_replay_after_revocation_confirms_finding():
    experiment, policy, redis = build_experiment()

    result = experiment.run("alice", "document-1", ttl_seconds=30)

    assert result.initial_authorization_status == 200
    assert result.cache_primed is True
    assert result.cached_canary == "remnant-canary-document-1-7b91c2e4"
    assert result.permission_revoked is True
    assert result.origin_status_after_revocation == 403
    assert result.cache_status == CacheStatus.HIT
    assert result.canary_match is True
    assert result.oracle_origin_denies is True
    assert result.oracle_cache_hit is True
    assert result.oracle_canary_matches is True
    assert result.finding_status == "CONFIRMED"
    assert policy.is_allowed(Principal("alice", Role.USER), "document-1").allowed is False
    assert len(redis.values) == 1


def test_experiment_uses_v2_observation_and_differential_pipeline():
    experiment, _, redis = build_experiment()

    result = experiment.run("alice", "document-1", ttl_seconds=30)

    assert result.cache_observation_status == "HIT"
    assert result.differential_state == "DIFFERENT"
    stored_payload = next(iter(redis.values.values()))[0]
    payload = json.loads(stored_payload)
    assert payload["metadata"]["principal_id"] == "alice"
    assert payload["metadata"]["resource_id"] == "document-1"
    assert payload["metadata"]["response_status"] == 200
    assert len(payload["metadata"]["body_sha256"]) == 64


def test_experiment_does_not_confirm_when_cache_metadata_identity_is_wrong():
    experiment, _, _ = build_experiment()
    original_store = experiment._cache.store

    def store_with_wrong_identity(key, response, *, ttl_seconds, metadata=None):
        from remnant.cache.metadata import CacheMetadata

        wrong = CacheMetadata.create(
            principal_id="mallory",
            resource_id="document-1",
            response_status=response.status_code,
            body=response.body,
            ttl_seconds=ttl_seconds,
        )
        return original_store(key, response, ttl_seconds=ttl_seconds, metadata=wrong)

    experiment._cache.store = store_with_wrong_identity
    result = experiment.run("alice", "document-1", ttl_seconds=30)

    assert result.cache_primed is False
    assert result.cache_observation_status == "INVALID_METADATA"
    assert result.oracle_cache_hit is False
    assert result.finding_status == "NOT_FOUND"


def test_oracle_does_not_confirm_when_origin_allows():
    oracle = evaluate_finding(
        origin_status=200,
        cache_status=CacheStatus.HIT,
        response_body=json.dumps({"canary": "expected"}).encode(),
        expected_canary="expected",
    )

    assert oracle.origin_denies is False
    assert oracle.cache_hit is True
    assert oracle.canary_matches is True
    assert oracle.finding_confirmed is False


def test_oracle_does_not_confirm_on_cache_miss():
    oracle = evaluate_finding(
        origin_status=403,
        cache_status=CacheStatus.MISS,
        response_body=None,
        expected_canary="expected",
    )

    assert oracle.origin_denies is True
    assert oracle.cache_hit is False
    assert oracle.canary_matches is False
    assert oracle.finding_confirmed is False


def test_oracle_does_not_confirm_when_canary_differs():
    oracle = evaluate_finding(
        origin_status=403,
        cache_status=CacheStatus.HIT,
        response_body=json.dumps({"canary": "different"}).encode(),
        expected_canary="expected",
    )

    assert oracle.origin_denies is True
    assert oracle.cache_hit is True
    assert oracle.canary_matches is False
    assert oracle.finding_confirmed is False


def test_experiment_cache_keys_are_isolated_by_principal_and_resource():
    experiment, _, redis = build_experiment()

    alice_document_1 = experiment.run("alice", "document-1")
    alice_document_2 = experiment.run("alice", "document-2")
    bob_document_1 = experiment.run("bob", "document-1")

    assert alice_document_1.resource_id == "document-1"
    assert alice_document_2.resource_id == "document-2"
    assert bob_document_1.principal_id == "bob"
    assert alice_document_1.cached_canary != alice_document_2.cached_canary
    assert len(redis.values) == 3
    key_suffixes = [key.removeprefix("unit:") for key in redis.values]
    assert any(key.endswith("protected:alice:document-1") for key in key_suffixes)
    assert any(key.endswith("protected:alice:document-2") for key in key_suffixes)
    assert any(key.endswith("protected:bob:document-1") for key in key_suffixes)


def test_each_run_primes_a_fresh_cache_entry():
    experiment, _, redis = build_experiment()

    first = experiment.run("alice", "document-1")
    second = experiment.run("alice", "document-1")

    assert first.experiment_id != second.experiment_id
    assert first.cache_prime_status is CacheStatus.MISS
    assert second.cache_prime_status is CacheStatus.MISS
    assert first.cache_primed is True
    assert second.cache_primed is True
    assert len(redis.values) == 2


def test_default_experiment_does_not_revoke_shared_application_grant(monkeypatch):
    shared_policy = AuthorizationPolicy()
    shared_policy.grant("alice", "document-1")
    monkeypatch.setattr(app_module, "authorization_policy", shared_policy)
    cache = RedisCacheManager(client=ExpiringRedis(), key_prefix="unit:")

    CacheReplayExperiment(cache=cache).run("alice", "document-1")

    assert shared_policy.is_allowed(Principal("alice", Role.USER), "document-1").allowed


def test_custom_origin_policy_is_used_by_experiment_when_policy_is_omitted():
    origin_policy = AuthorizationPolicy()
    origin = create_protected_origin_app(origin_policy)
    experiment = CacheReplayExperiment(
        cache=RedisCacheManager(client=ExpiringRedis(), key_prefix="unit:"),
        origin_app=origin,
    )

    result = experiment.run("alice", "document-1")

    assert result.finding_status == "CONFIRMED"
    assert result.permission_revoked is True
    assert result.origin_status_after_revocation == 403


def test_different_experiment_and_origin_policies_are_rejected():
    experiment_policy = AuthorizationPolicy()
    origin = create_protected_origin_app(AuthorizationPolicy())

    with pytest.raises(ValueError, match="same AuthorizationPolicy"):
        CacheReplayExperiment(
            cache=RedisCacheManager(client=ExpiringRedis()),
            policy=experiment_policy,
            origin_app=origin,
        )


def test_expired_cache_entry_does_not_confirm_finding():
    experiment, policy, redis = build_experiment()
    original_revoke = policy.revoke

    def revoke_and_expire(principal_id, resource_id):
        original_revoke(principal_id, resource_id)
        redis.now += 1

    policy.revoke = revoke_and_expire
    result = experiment.run("alice", "document-1", ttl_seconds=1)

    assert result.cache_status is CacheStatus.MISS
    assert result.finding_status == "NOT_FOUND"


def test_failed_cache_priming_does_not_confirm_finding():
    experiment, _, redis = build_experiment()
    experiment._cache.store = lambda *args, **kwargs: None

    result = experiment.run("alice", "document-1")

    assert result.cache_primed is False
    assert result.cache_status is CacheStatus.MISS
    assert result.finding_status == "NOT_FOUND"
    assert redis.values == {}


def test_failed_permission_revocation_does_not_confirm_finding():
    experiment, policy, _ = build_experiment()
    policy.revoke = lambda principal_id, resource_id: None

    result = experiment.run("alice", "document-1")

    assert result.permission_revoked is False
    assert result.origin_status_after_revocation == 200
    assert result.finding_status == "NOT_FOUND"


@pytest.mark.parametrize(
    "body",
    [
        b'{"resource_id":"document-1"}',
        b'["remnant-canary-document-1-7b91c2e4"]',
        b'{malformed json',
    ],
    ids=["missing-canary", "non-object-json", "malformed-json"],
)
def test_invalid_cached_json_does_not_confirm_finding(body):
    oracle = evaluate_finding(
        origin_status=403,
        cache_status=CacheStatus.HIT,
        response_body=body,
        expected_canary="remnant-canary-document-1-7b91c2e4",
    )

    assert oracle.cache_hit is True
    assert oracle.canary_matches is False
    assert oracle.finding_confirmed is False


def test_unexpected_origin_http_status_does_not_confirm_finding():
    oracle = evaluate_finding(
        origin_status=502,
        cache_status=CacheStatus.HIT,
        response_body=json.dumps(
            {"canary": "remnant-canary-document-1-7b91c2e4"}
        ).encode(),
        expected_canary="remnant-canary-document-1-7b91c2e4",
    )

    assert oracle.origin_denies is False
    assert oracle.cache_hit is True
    assert oracle.canary_matches is True
    assert oracle.finding_confirmed is False



class RecordingOriginAdapter:
    def __init__(self, policy):
        from remnant.origin.fastapi import FastAPIOriginAdapter

        self._adapter = FastAPIOriginAdapter(create_protected_origin_app(policy))
        self.calls = []

    async def get_protected(self, resource_id, *, principal_id):
        self.calls.append((resource_id, principal_id))
        return await self._adapter.get_protected(
            resource_id, principal_id=principal_id
        )


def test_experiment_routes_all_origin_requests_through_injected_adapter():
    policy = AuthorizationPolicy()
    adapter = RecordingOriginAdapter(policy)
    cache = RedisCacheManager(client=ExpiringRedis(), key_prefix="adapter:")
    experiment = CacheReplayExperiment(
        cache=cache, policy=policy, origin_adapter=adapter
    )

    result = experiment.run("alice", "document-1")

    assert result.finding_status == "CONFIRMED"
    assert adapter.calls == [
        ("document-1", "alice"),
        ("document-1", "alice"),
        ("document-1", "alice"),
    ]


def test_experiment_rejects_both_origin_app_and_adapter():
    policy = AuthorizationPolicy()
    adapter = RecordingOriginAdapter(policy)
    with pytest.raises(ValueError, match="origin_adapter or origin_app"):
        CacheReplayExperiment(
            cache=RedisCacheManager(client=ExpiringRedis()),
            policy=policy,
            origin_app=create_protected_origin_app(policy),
            origin_adapter=adapter,
        )


def test_sync_experiment_fails_clearly_inside_running_event_loop():
    import asyncio

    experiment, _, _ = build_experiment()

    async def invoke():
        with pytest.raises(RuntimeError, match="running event loop"):
            experiment.run("alice", "document-1")

    asyncio.run(invoke())
    assert experiment._policy.is_allowed(
        Principal("alice", Role.USER), "document-1"
    ).allowed is False



def test_experiment_analysis_evidence_is_serializable_and_body_free():
    experiment, _, _ = build_experiment()
    result = experiment.run("alice", "document-1")

    evidence = result.analysis_evidence
    assert evidence is not None
    payload = evidence.to_dict()
    encoded = json.dumps(payload, sort_keys=True)

    assert payload["schema_version"] == 1
    assert payload["initial_origin_status"] == 200
    assert payload["cache_prime_observation_status"] == "HIT"
    assert payload["cache_prime_metadata"]["present"] is True
    assert payload["cache_prime_metadata"]["valid"] is True
    assert payload["cache_prime_metadata"]["principal_id"] == "alice"
    assert payload["cache_prime_metadata"]["resource_id"] == "document-1"
    assert payload["post_revocation_origin_status"] == 403
    assert payload["replay_observation_status"] == "HIT"
    assert payload["replay_metadata"]["valid"] is True
    assert payload["differential"]["state"] == "DIFFERENT"
    assert set(payload["differential"]) >= {
        "status_code", "selected_headers", "body_digest", "canary"
    }
    assert "remnant-canary-document-1-7b91c2e4" not in encoded
    assert "response_body" not in encoded
    assert "cache_key" not in encoded


def test_analysis_evidence_records_safe_metadata_mismatch_category():
    experiment, _, _ = build_experiment()
    original_store = experiment._cache.store

    def store_with_wrong_identity(key, response, *, ttl_seconds, metadata=None):
        from remnant.cache.metadata import CacheMetadata

        wrong = CacheMetadata.create(
            principal_id="mallory",
            resource_id="document-1",
            response_status=response.status_code,
            body=response.body,
            ttl_seconds=ttl_seconds,
        )
        return original_store(key, response, ttl_seconds=ttl_seconds, metadata=wrong)

    experiment._cache.store = store_with_wrong_identity
    result = experiment.run("alice", "document-1")

    evidence = result.analysis_evidence
    assert evidence is not None
    assert "METADATA_IDENTITY_MISMATCH" in evidence.diagnostic_categories
    assert evidence.replay_observation_status == "INVALID_METADATA"
    assert evidence.replay_metadata.valid is False
