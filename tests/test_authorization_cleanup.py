import pytest

from remnant.auth.models import Principal, Role
from remnant.auth.policy import AuthorizationPolicy
from remnant.cache.manager import RedisCacheManager
from remnant.engine.experiment import CacheReplayExperiment


class MemoryRedis:
    def set(self, key, value, *, ex):
        return True

    def get(self, key):
        return None

    def delete(self, key):
        return 0


class FailingOrigin:
    async def get_protected(self, resource_id: str, *, principal_id: str):
        raise RuntimeError("simulated origin failure")


def test_temporary_grant_is_revoked_when_initial_origin_request_fails():
    policy = AuthorizationPolicy()
    experiment = CacheReplayExperiment(
        cache=RedisCacheManager(client=MemoryRedis()),
        policy=policy,
        origin_adapter=FailingOrigin(),
    )

    with pytest.raises(RuntimeError, match="simulated origin failure"):
        experiment.run("alice", "document-1")

    decision = policy.is_allowed(
        Principal(principal_id="alice", role=Role.USER),
        "document-1",
    )
    assert decision.allowed is False
    assert decision.reason == "no_active_grant"
