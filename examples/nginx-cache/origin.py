"""Tiny stateful protected origin used only by the Nginx cache integration lab."""

from fastapi import FastAPI, HTTPException

app = FastAPI(title="REMNANT Nginx cache test origin")
_grants: set[str] = set()
CANARY = "remnant-nginx-canary-private-report-8f31"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/admin/grant/{principal_id}")
def grant(principal_id: str) -> dict[str, str]:
    _grants.add(principal_id)
    return {"principal_id": principal_id, "access": "granted"}


@app.post("/admin/revoke/{principal_id}")
def revoke(principal_id: str) -> dict[str, str]:
    _grants.discard(principal_id)
    return {"principal_id": principal_id, "access": "revoked"}


@app.get("/protected/report")
def protected_report(principal_id: str) -> dict[str, str]:
    if principal_id not in _grants:
        raise HTTPException(status_code=403, detail="Forbidden")
    return {
        "resource": "private-report",
        "principal_id": principal_id,
        "content": "Controlled confidential report fixture",
        "canary": CANARY,
    }
