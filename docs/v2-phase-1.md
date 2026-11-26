# REMNANT V2 — Phase 1 foundation

Phase 1 introduces a new authorization model and a declarative scenario foundation while preserving the V1 AuthorizationPolicy API and V1 experiment oracle.

## V2 authorization model

The new PolicyEngine evaluates requests in this order:

1. Identity exists and is active.
2. Identity tenant exists and is active.
3. Resource exists.
4. Identity and resource belong to the same tenant.
5. An explicit denial is absent.
6. Resource ownership grants the supported owner actions.
7. An explicit permission grant is present.
8. A tenant-admin role grants its supported actions within that tenant.
9. Otherwise, deny by default.

Tenant boundaries are evaluated before owner, grant, or administrator rules. An administrator role in V2 is tenant-scoped and cannot cross the tenant boundary.

The V1 AuthorizationPolicy remains available and retains its original grant/revoke and administrator semantics. V1 routes and experiments are not migrated implicitly.

## Identity and resource lifecycle

IdentityRegistry supports registration, role changes, suspension, reactivation, and removal. Removed identities cannot be reactivated. ResourceRegistry stores resource ownership and tenant association. TenantRegistry stores tenant activation state.

All registries are in-memory test components. Persistence is intentionally deferred to a later phase.

## Declarative scenarios

ScenarioLoader reads YAML and JSON documents. ScenarioValidator checks the schema version, unique identifiers, tenant references, resource ownership, supported actions, and step references.

ScenarioTransitionEngine provides a deterministic logical dry-run for permission, identity and cache-prime state transitions. It performs no HTTP requests and does not claim to execute the full cache/origin experiment. Network execution and adapters are deferred to later phases.

## Security boundaries

This is a controlled test framework foundation, not a production identity provider or multi-tenant application authorization middleware. The in-memory registries are process-local. A V2 scenario's successful validation proves structural consistency, not that a live service enforces the same policy.

## Compatibility

Existing V1 imports and tests continue to use AuthorizationPolicy. The V2 PolicyEngine is a separate implementation with explicit tenant-aware semantics. The original three-condition V1 finding oracle is not changed by this phase.
