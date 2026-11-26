from remnant.auth.models import Resource


class ResourceRegistry:
    """Registry for tenant-owned resources used by the V2 policy engine."""

    def __init__(self) -> None:
        self._resources: dict[str, Resource] = {}
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    def register(self, resource: Resource) -> Resource:
        for name, value in (("resource_id", resource.resource_id),
                            ("tenant_id", resource.tenant_id),
                            ("owner_id", resource.owner_id)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} cannot be empty")
        if resource.resource_id in self._resources:
            raise ValueError(f"resource already exists: {resource.resource_id}")
        self._resources[resource.resource_id] = resource
        self._version += 1
        return resource

    def get(self, resource_id: str) -> Resource | None:
        if not isinstance(resource_id, str) or not resource_id.strip():
            raise ValueError("resource_id cannot be empty")
        return self._resources.get(resource_id)

    def remove(self, resource_id: str) -> Resource:
        try:
            resource = self._resources.pop(resource_id)
            self._version += 1
            return resource
        except KeyError as exc:
            raise KeyError(f"unknown resource: {resource_id}") from exc

    def list_resources(self) -> tuple[Resource, ...]:
        return tuple(self._resources[key] for key in sorted(self._resources))
