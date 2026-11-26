import json

import pytest

from remnant.v3.identity_isolation import IsolationStatus, evaluate_identity_isolation


def run(**overrides):
    args = dict(
        requester_id="alice", owner_id="bob", origin_status=403,
        proxy_status=200, proxy_cache_state="hit",
        proxy_body=json.dumps({"canary": "bob-private"}).encode(),
        expected_owner_canary="bob-private",
    )
    args.update(overrides)
    return evaluate_identity_isolation(**args)


def test_confirms_cross_identity_cached_disclosure_only_with_all_conditions():
    assert run().status is IsolationStatus.CONFIRMED


@pytest.mark.parametrize("overrides", [
    {"origin_status": 200}, {"proxy_status": 403},
    {"proxy_cache_state": "miss"},
    {"proxy_body": b'{"canary":"other"}'},
])
def test_does_not_confirm_without_all_conditions(overrides):
    assert run(**overrides).status is IsolationStatus.NOT_CONFIRMED


def test_unknown_cache_state_is_indeterminate():
    assert run(proxy_cache_state="unknown").status is IsolationStatus.INDETERMINATE


def test_same_identity_is_rejected():
    with pytest.raises(ValueError, match="distinct"):
        run(requester_id="bob", owner_id="bob")
