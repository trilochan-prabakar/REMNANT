import hashlib

import pytest

from remnant.cache.metadata import CacheMetadata
from remnant.cache.models import CacheObservation, CacheObservationStatus
from remnant.cache.manager import CachedHTTPResponse


def test_metadata_round_trip_and_body_digest():
    metadata = CacheMetadata.create(
        principal_id="alice",
        resource_id="document-1",
        tenant_id="tenant-a",
        response_status=200,
        body=b"secret snapshot",
        ttl_seconds=30,
        now=100.0,
    )

    restored = CacheMetadata.from_dict(metadata.to_dict())

    assert restored == metadata
    assert restored.verify_body(b"secret snapshot")
    assert not restored.verify_body(b"tampered snapshot")
    assert metadata.body_sha256 == hashlib.sha256(b"secret snapshot").hexdigest()
    assert metadata.expires_at == 130.0


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"principal_id": ""},
        {"resource_id": " "},
        {"response_status": True},
        {"response_status": 99},
        {"body_sha256": "not-a-digest"},
        {"expires_at": 0.5},
        {"unexpected": "field"},
    ],
)
def test_invalid_metadata_is_rejected(changes):
    data = CacheMetadata.create(
        principal_id="alice", resource_id="doc", response_status=200,
        body=b"body", ttl_seconds=10, now=1.0,
    ).to_dict()
    data.update(changes)

    with pytest.raises(ValueError):
        CacheMetadata.from_dict(data)


def test_metadata_rejects_missing_fields_and_non_object_input():
    with pytest.raises(ValueError, match="missing or unexpected"):
        CacheMetadata.from_dict({"schema_version": 1})
    with pytest.raises(ValueError, match="must be an object"):
        CacheMetadata.from_dict([])


@pytest.mark.parametrize("ttl", [0, -1, 1.5, True])
def test_metadata_rejects_invalid_ttl(ttl):
    with pytest.raises(ValueError, match="positive integer"):
        CacheMetadata.create(
            principal_id="alice", resource_id="doc", response_status=200,
            body=b"body", ttl_seconds=ttl, now=1.0,
        )


def test_cache_observation_enforces_hit_evidence():
    response = CachedHTTPResponse(200, (), b"body")
    assert CacheObservation(CacheObservationStatus.HIT, response=response).response == response

    with pytest.raises(ValueError, match="requires a response"):
        CacheObservation(CacheObservationStatus.HIT)
    with pytest.raises(ValueError, match="only a HIT"):
        CacheObservation(CacheObservationStatus.MISS, response=response)



@pytest.mark.parametrize("timestamp", [float("nan"), float("inf"), float("-inf")])
def test_metadata_rejects_non_finite_creation_timestamp(timestamp):
    with pytest.raises(ValueError, match="finite numeric"):
        CacheMetadata.create(
            principal_id="alice", resource_id="doc", response_status=200,
            body=b"body", ttl_seconds=10, now=timestamp,
        )


@pytest.mark.parametrize("field", ["created_at", "expires_at"])
@pytest.mark.parametrize("timestamp", [float("nan"), float("inf"), float("-inf")])
def test_metadata_rejects_non_finite_stored_timestamps(field, timestamp):
    data = CacheMetadata.create(
        principal_id="alice", resource_id="doc", response_status=200,
        body=b"body", ttl_seconds=10, now=1.0,
    ).to_dict()
    data[field] = timestamp

    with pytest.raises(ValueError, match="finite numeric"):
        CacheMetadata.from_dict(data)


def test_metadata_accepts_large_integer_timestamps_without_float_overflow():
    metadata = CacheMetadata.create(
        principal_id="alice",
        resource_id="doc",
        response_status=200,
        body=b"body",
        ttl_seconds=10,
        now=10**400,
    )

    assert metadata.created_at == 10**400
    assert metadata.expires_at == 10**400 + 10
