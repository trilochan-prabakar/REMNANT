"""Tenant-aware protected origin app for the selectable V2 experiment path."""

from fastapi import FastAPI, HTTPException, Query

from remnant.api.app import PROTECTED_RESOURCES
from remnant.auth.adapter import PolicyEngineAdapter


def create_v2_protected_origin_app(adapter: PolicyEngineAdapter) -> FastAPI:
    """Create an origin whose tenant context is resolved only from trusted registries."""
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
        resource = PROTECTED_RESOURCES.get(resource_id)
        if resource is None:
            raise HTTPException(status_code=404, detail="Resource not found")
        return {"resource_id": resource_id, **resource}

    return origin
