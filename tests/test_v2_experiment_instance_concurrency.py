import json
from threading import Event, Thread

import pytest

from remnant.auth.models import Principal, Role
from remnant.auth.policy import AuthorizationPolicy
from remnant.cache.manager import RedisCacheManager
from remnant.engine.experiment import CacheReplayExperiment
from remnant.origin.protocols import OriginResponse


class MemoryRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, *, ex):
        self.values[key] = value
        return True

    def delete(self, key):
        return int(self.values.pop(key, None) is not None)


class BlockingOrigin:
    def __init__(self, policy, started, release):
        self.policy = policy
        self.started = started
        self.release = release
        self.first_call = True

    async def get_protected(self, resource_id, *, principal_id):
        if self.first_call:
            self.first_call = False
            self.started.set()
            if not self.release.wait(timeout=5):
                raise RuntimeError("test did not release blocking origin")
        allowed = self.policy.is_allowed(
            Principal(principal_id, Role.USER), resource_id
        ).allowed
        status = 200 if allowed else 403
        body = (
            json.dumps({
                "resource_id": resource_id,
                "canary": "remnant-canary-document-1-7b91c2e4",
            }).encode()
            if allowed else b'{"detail":"Forbidden"}'
        )
        return OriginResponse(status, (("content-type", "application/json"),), body)


def test_same_experiment_instance_rejects_overlapping_run_calls():
    policy = AuthorizationPolicy()
    started = Event()
    release = Event()
    experiment = CacheReplayExperiment(
        cache=RedisCacheManager(client=MemoryRedis()),
        policy=policy,
        origin_adapter=BlockingOrigin(policy, started, release),
    )
    outcomes = []

    def run_first():
        try:
            outcomes.append(experiment.run("alice", "document-1"))
        except Exception as exc:  # surfaced in the main test thread below
            outcomes.append(exc)

    worker = Thread(target=run_first)
    worker.start()
    try:
        assert started.wait(timeout=3), "first run did not reach the origin adapter"
        with pytest.raises(RuntimeError, match="already running"):
            experiment.run("bob", "document-1")
    finally:
        release.set()
        worker.join(timeout=5)

    assert not worker.is_alive()
    assert len(outcomes) == 1
    assert not isinstance(outcomes[0], Exception)
    assert outcomes[0].finding_status == "CONFIRMED"
