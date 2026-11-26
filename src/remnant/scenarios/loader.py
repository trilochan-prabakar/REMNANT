import json
from pathlib import Path
from typing import Any

import yaml

from remnant.scenarios.models import (
    Scenario, ScenarioIdentity, ScenarioResource, ScenarioStep,
)


class ScenarioLoader:
    """Load versioned REMNANT scenario files from YAML or JSON."""

    def load(self, path: str | Path) -> Scenario:
        source = Path(path)
        text = source.read_text(encoding="utf-8")
        return self.loads(text, format=source.suffix.lstrip(".").lower())

    def loads(self, text: str, *, format: str | None = None) -> Scenario:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("scenario document cannot be empty")
        selected = (format or "").lower()
        if selected == "json" or (not selected and text.lstrip().startswith(("{", "["))):
            data = json.loads(text)
        elif selected in {"", "yaml", "yml"}:
            data = yaml.safe_load(text)
        else:
            raise ValueError(f"unsupported scenario format: {selected}")
        return self.from_mapping(data)

    @staticmethod
    def from_mapping(data: Any) -> Scenario:
        if not isinstance(data, dict):
            raise ValueError("scenario document must be a mapping")
        scenario_data = data.get("scenario")
        if not isinstance(scenario_data, dict):
            raise ValueError("'scenario' must be a mapping")

        tenants_data = data.get("tenants", [])
        identities_data = data.get("identities", [])
        resources_data = data.get("resources", [])
        steps_data = scenario_data.get("steps", data.get("steps", []))
        for field, value in (
            ("tenants", tenants_data), ("identities", identities_data),
            ("resources", resources_data), ("steps", steps_data),
        ):
            if not isinstance(value, list):
                raise ValueError(f"'{field}' must be a list")

        identities = tuple(
            ScenarioIdentity(
                identity_id=item["id"],
                tenant_id=item["tenant"],
                roles=tuple(item.get("roles", ["user"])),
            )
            for item in identities_data
            if isinstance(item, dict)
        )
        if len(identities) != len(identities_data):
            raise ValueError("each identity must be a mapping")

        resources = tuple(
            ScenarioResource(
                resource_id=item["id"],
                tenant_id=item["tenant"],
                owner_id=item["owner"],
            )
            for item in resources_data
            if isinstance(item, dict)
        )
        if len(resources) != len(resources_data):
            raise ValueError("each resource must be a mapping")

        steps = tuple(
            ScenarioStep(
                action=item["action"],
                principal=item.get("principal"),
                resource=item.get("resource"),
                permission=item.get("permission", "read"),
            )
            for item in steps_data
            if isinstance(item, dict)
        )
        if len(steps) != len(steps_data):
            raise ValueError("each step must be a mapping")

        return Scenario(
            scenario_id=scenario_data["id"],
            name=scenario_data["name"],
            schema_version=scenario_data.get("schema_version", data.get("schema_version", 1)),
            tenants=tuple(item["id"] if isinstance(item, dict) else item for item in tenants_data),
            identities=identities,
            resources=resources,
            steps=steps,
        )
