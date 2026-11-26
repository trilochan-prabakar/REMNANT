from fastapi import FastAPI, HTTPException, Query, Request

from remnant.auth.models import (
    AuthorizationDecision,
    Principal,
    Role,
)
from remnant.auth.policy import AuthorizationPolicy


API_VERSION = "2.0.0"
authorization_policy = AuthorizationPolicy()

PROTECTED_RESOURCES: dict[str, dict[str, str]] = {
    "document-1": {
        "content": "Confidential project notes for document one.",
        "canary": "remnant-canary-document-1-7b91c2e4",
    },
    "document-2": {
        "content": "Confidential project notes for document two.",
        "canary": "remnant-canary-document-2-d45a08f3",
    },
}

app = FastAPI(
    title="REMNANT",
    description="Stateful Cache–Authorization Consistency Testing Framework",
    version=API_VERSION,
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "project": "REMNANT",
        "version": API_VERSION,
    }


@app.get("/protected/{resource_id}")
async def get_protected_resource(
    request: Request,
    resource_id: str,
    principal_id: str = Query(..., min_length=1),
) -> dict[str, str]:
    principal = Principal(principal_id=principal_id, role=Role.USER)
    try:
        policy: AuthorizationPolicy = getattr(
            request.app.state,
            "authorization_policy",
            authorization_policy,
        )
        decision: AuthorizationDecision = policy.is_allowed(
            principal,
            resource_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid principal or resource",
        ) from exc

    if not decision.allowed:
        raise HTTPException(status_code=403, detail="Forbidden")

    resource = PROTECTED_RESOURCES.get(resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    return {
        "resource_id": resource_id,
        **resource,
    }


def create_protected_origin_app(policy: AuthorizationPolicy) -> FastAPI:
    """Create an isolated protected origin using the supplied policy."""
    origin = FastAPI(title="REMNANT protected origin", version=API_VERSION)
    origin.state.authorization_policy = policy
    origin.add_api_route(
        "/protected/{resource_id}",
        get_protected_resource,
        methods=["GET"],
    )
    return origin
