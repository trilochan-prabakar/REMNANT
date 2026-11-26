"""Tenant-aware protected origin app for the selectable V2 experiment path."""

import hashlib

from fastapi import FastAPI, HTTPException, Query

from remnant.api.app import PROTECTED_RESOURCES
from remnant.auth.adapter import PolicyEngineAdapter


def resource_canary(resource_id: str) -> str:
    """Return a stable, resource-specific canary for registry-defined fixtures."""
    digest = hashlib.sha256(resource_id.encode("utf-8")).hexdigest()[:8]
    return f"remnant-canary-{resource_id}-{digest}"


def create_v2_protected_origin_app(adapter: PolicyEngineAdapter) -> FastAPI:
    """Create an origin whose resource and tenant context come from trusted registries."""
    origin = FastAPI(title="REMNANT V2 tenant-aware protected origin")
    origin.state.authorization_policy = adapter

    @origin.get("/protected/{resource_id}")
    async def get_protected_resource(
        resource_id: str,
        principal_id: str = Query(..., min_length=1),
    ) -> dict[str, str]:
        decision = adapter.engine.evaluate(principal_id, resource_id, "read")
        if not decision.allowed:
            raise HTTPException(status_code=403, detail="Forbidden")

        # The policy decision proves that the identity and resource are registered
        # and tenant-compatible. Do not use the V1 sample catalogue as the V2
        # resource registry: V2 callers may register their own resource IDs.
        registered = adapter.engine.resources.get(resource_id)
        if registered is None:
            raise HTTPException(status_code=404, detail="Resource not found")

        sample = PROTECTED_RESOURCES.get(resource_id)
        if sample is not None:
            payload = sample
        else:
            payload = {
                "content": f"Confidential test content for resource {resource_id}.",
                "canary": resource_canary(resource_id),
            }
        return {"resource_id": resource_id, **payload}

    return origin
