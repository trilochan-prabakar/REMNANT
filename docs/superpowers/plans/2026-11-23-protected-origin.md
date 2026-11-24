# Protected Origin Application Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an origin endpoint that checks the existing policy and serves fixed protected resources with stable canaries.

**Architecture:** Register a direct route in the existing FastAPI application. Store the current `AuthorizationPolicy` and fixed resources in `app.py`; create user principals from the required `principal_id` query parameter and call the policy for each request.

**Tech Stack:** Python 3.12, FastAPI, pytest, httpx ASGI transport.

**Spec:** `docs/superpowers/specs/2026-11-23-protected-origin-design.md`

## Global Constraints

- Reuse existing authorization models and `AuthorizationPolicy`.
- Do not modify Redis Cache Manager or add caching/replay behavior.
- Preserve `/health` behavior and existing project conventions.
- Authorized requests return HTTP 200 with protected content; denied requests return HTTP 403 without protected content or canary.

## Review Focus

- Missing `principal_id` must be rejected by FastAPI without exposing a resource; cover in the endpoint test task.
- Resource ids must remain isolated by policy grant; cover in the endpoint test task.
- A revoked grant must deny the next request while preserving another principal's grant; cover in the endpoint test task.

---

### Task 1: Protected origin endpoint

**Files:**
- Modify: `src/remnant/api/app.py`
- Create: `tests/test_origin.py`

**Interfaces:**
- Consumes: `AuthorizationPolicy.grant(principal_id: str, resource_id: str)`, `revoke(...)`, and `is_allowed(principal: Principal, resource_id: str) -> AuthorizationDecision`.
- Produces: `GET /protected/{resource_id}?principal_id=<id>`; successful JSON includes `resource_id`, `content`, and `canary`.

- [x] **Step 1: Write focused endpoint tests first.** Cover the exact successful resource payload and stable canary, denied 403 response with no content/canary, immediate revocation, isolation between principals and resources, and missing principal rejection. The existing `tests/test_health.py` covers continued `/health` behavior in the full suite.
- [x] **Step 2: Run `pytest tests/test_origin.py -q` and confirm it fails because the protected route is missing.**
- [x] **Step 3: Add fixed protected resources with distinct stable canaries and a shared policy instance; implement the route so it constructs a `Role.USER` principal and checks policy before reading/returning the resource.**
- [x] **Step 4: Run `pytest tests/test_origin.py -q` and confirm all focused tests pass.**
- [x] **Step 5: Run `pytest -q` and confirm the complete suite passes, including the existing Redis integration test when Redis is available.**
