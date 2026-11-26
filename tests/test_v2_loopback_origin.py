"""Real loopback HTTP integration tests for the network origin adapter."""

import asyncio
import socket
import threading
import time

import pytest
import uvicorn
from redis import Redis

from remnant.cache.manager import RedisCacheManager
from remnant.engine.experiment import CacheReplayExperiment

from remnant.api.app import create_protected_origin_app
from remnant.auth.policy import AuthorizationPolicy
from remnant.origin import LoopbackHTTPOriginAdapter, OriginAdapter
from remnant.origin.fastapi import OriginTransportError


@pytest.fixture
def live_origin():
    policy = AuthorizationPolicy()
    app = create_protected_origin_app(policy)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="critical",
            access_log=False,
            lifespan="off",
        )
    )
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [listener]},
        daemon=True,
    )
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=2)
        listener.close()
        pytest.fail("loopback origin server did not become ready")

    try:
        yield policy, f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if thread.is_alive():
            server.force_exit = True
            thread.join(timeout=2)
        listener.close()
        assert not thread.is_alive(), "loopback origin server did not shut down"


def request(adapter, resource_id="document-1", principal_id="alice"):
    return asyncio.run(
        adapter.get_protected(resource_id, principal_id=principal_id)
    )


def test_loopback_adapter_satisfies_origin_protocol(live_origin):
    _, base_url = live_origin
    adapter = LoopbackHTTPOriginAdapter(base_url)
    assert isinstance(adapter, OriginAdapter)


def test_loopback_adapter_reaches_real_http_origin_and_returns_content(live_origin):
    policy, base_url = live_origin
    policy.grant("alice", "document-1")

    response = request(LoopbackHTTPOriginAdapter(base_url))

    assert response.status_code == 200
    assert b'"resource_id":"document-1"' in response.body
    assert b"remnant-canary-document-1-7b91c2e4" in response.body


def test_loopback_adapter_observes_origin_revocation(live_origin):
    policy, base_url = live_origin
    adapter = LoopbackHTTPOriginAdapter(base_url)
    policy.grant("alice", "document-1")
    assert request(adapter).status_code == 200

    policy.revoke("alice", "document-1")

    denied = request(adapter)
    assert denied.status_code == 403
    assert b"remnant-canary-document-1-7b91c2e4" not in denied.body


@pytest.mark.parametrize(
    "base_url",
    [
        "http://example.com:8080",
        "http://192.0.2.10:8080",
        "ftp://127.0.0.1:8080",
        "http://user:password@127.0.0.1:8080",
        "http://127.0.0.1:8080/path",
        "http://127.0.0.1:8080?redirect=1",
        "http://127.0.0.1",
    ],
)
def test_loopback_adapter_rejects_non_loopback_or_ambiguous_urls(base_url):
    with pytest.raises(ValueError):
        LoopbackHTTPOriginAdapter(base_url)


@pytest.mark.parametrize("timeout", [0, -1, True, float("inf")])
def test_loopback_adapter_rejects_invalid_timeouts(timeout):
    with pytest.raises(ValueError):
        LoopbackHTTPOriginAdapter("http://127.0.0.1:8080", timeout_seconds=timeout)


def test_loopback_adapter_rejects_empty_request_identity(live_origin):
    _, base_url = live_origin
    adapter = LoopbackHTTPOriginAdapter(base_url)
    with pytest.raises(ValueError):
        request(adapter, resource_id="", principal_id="alice")
    with pytest.raises(ValueError):
        request(adapter, resource_id="document-1", principal_id="")


def test_loopback_adapter_wraps_connection_failure_as_transport_error():
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    adapter = LoopbackHTTPOriginAdapter(
        f"http://127.0.0.1:{port}", timeout_seconds=0.5
    )

    with pytest.raises(OriginTransportError, match="loopback origin request failed"):
        request(adapter)


def test_full_experiment_uses_loopback_origin_and_real_redis(live_origin):
    policy, base_url = live_origin
    policy.grant("alice", "document-1")
    cache = RedisCacheManager(
        redis_url="redis://localhost:6379/0",
        key_prefix=f"remnant:phase4-loopback:{__import__('uuid').uuid4().hex}:",
    )
    experiment = CacheReplayExperiment(
        cache=cache,
        policy=policy,
        origin_adapter=LoopbackHTTPOriginAdapter(base_url),
    )

    try:
        Redis.from_url("redis://localhost:6379/0").ping()
        result = experiment.run("alice", "document-1")
        assert result.finding_status == "CONFIRMED"
        assert result.origin_status_after_revocation == 403
        assert result.cache_observation_status == "HIT"
        assert result.oracle_origin_denies is True
        assert result.oracle_cache_hit is True
        assert result.oracle_canary_matches is True
    finally:
        if "result" in locals():
            cache.delete(
                experiment._cache_key(
                    result.experiment_id, "alice", "document-1"
                )
            )
