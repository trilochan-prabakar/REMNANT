# Protected Origin Application Design

## Intent

Add an origin endpoint that checks the existing authorization policy on each request before returning protected content. REMNANT will later compare origin decisions with cached responses.

## Goals and constraints

- Reuse `AuthorizationPolicy`, `Principal`, `Role`, and `AuthorizationDecision` through the existing policy API.
- Serve protected resources with stable, unique canaries only after authorization.
- Keep `/health` working and leave Redis/cache code untouched.
- Keep this phase limited to the protected origin endpoint and its tests.

## Approach

Add `GET /protected/{resource_id}` to the existing FastAPI app. The caller identifies itself with the required `principal_id` query parameter; all request identities are constructed as `Role.USER`, so callers cannot choose an elevated role. A module-level `AuthorizationPolicy` instance holds current grants, and every request calls `is_allowed` before reading from a fixed in-memory resource map. Authorized responses contain the resource id, content, and stable canary; denied responses are generic 403 responses. Existing in-memory grant and revoke calls affect the next request immediately.

An injected router with app-state dependencies was considered, but the app currently has only a health route and no dependency wiring. The direct route is the smallest fit for the existing architecture.

## Request example

`GET /protected/document-1?principal_id=alice`

The endpoint returns the resource only after `AuthorizationPolicy` permits Alice to access `document-1`. Grant and revoke operations remain internal policy operations; this phase does not add a permission-management API.

## Non-goals

No Redis integration, caching, cache replay, invalidation, vulnerability detection, reporting, or later project phases.
