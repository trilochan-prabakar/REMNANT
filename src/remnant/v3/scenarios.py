"""Strict, versioned V3 scenario format for controlled HTTP cache experiments."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

import yaml


class ScenarioFormatError(ValueError):
    """A scenario is malformed or attempts an unsupported operation."""


@dataclass(frozen=True)
class RequestStep:
    name: str
    via: str
    method: str
    path: str
    headers: tuple[tuple[str, str], ...] = ()
    expected_status: int | None = None
    expected_cache_state: str | None = None
    expected_body_contains: str | None = None


@dataclass(frozen=True)
class ControlStep:
    """A constrained test-fixture control action; never an arbitrary URL or method."""
    name: str
    operation: str
    via: str
    principal: str | None = None
    path: str | None = None
    expected_status: int = 200


ScenarioStep = RequestStep | ControlStep


@dataclass(frozen=True)
class ScenarioDefinition:
    scenario_id: str
    name: str
    description: str
    steps: tuple[ScenarioStep, ...]
    schema_version: int = 1


class ScenarioLoader:
    """Load safe YAML scenario documents; URLs and executable code are not accepted."""

    ROOT_KEYS = {"scenario", "steps"}
    REQUEST_KEYS = {
        "type", "name", "via", "method", "path", "headers",
        "expect_status", "expect_cache_state", "expect_body_contains",
    }
    CONTROL_KEYS = {"type", "name", "operation", "via", "principal", "path", "expect_status"}
    CACHE_STATES = {"hit", "miss", "stale", "bypass", "unknown"}

    @staticmethod
    def _path(path: object, index: int) -> str:
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
            raise ScenarioFormatError(f"step {index}: path must be an absolute-path reference")
        parsed = urlsplit(path)
        decoded_path = unquote(parsed.path)
        if (
            parsed.scheme or parsed.netloc or parsed.fragment or "\\" in path
            or "\\" in decoded_path
            or any(ord(char) < 32 or ord(char) == 127 for char in path)
            or any(part in {".", ".."} for part in decoded_path.split("/"))
        ):
            raise ScenarioFormatError(f"step {index}: absolute URLs, fragments, controls, and path traversal are forbidden")
        return path

    def loads(self, text: str) -> ScenarioDefinition:
        if not isinstance(text, str) or not text.strip():
            raise ScenarioFormatError("scenario document cannot be empty")
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ScenarioFormatError(f"invalid YAML: {exc}") from exc
        if not isinstance(raw, dict) or set(raw) != self.ROOT_KEYS:
            raise ScenarioFormatError("document must contain exactly 'scenario' and 'steps'")
        meta, steps_raw = raw["scenario"], raw["steps"]
        if not isinstance(meta, dict) or set(meta) - {"id", "name", "description", "schema_version"}:
            raise ScenarioFormatError("'scenario' must be a mapping with supported fields")
        version = meta.get("schema_version", 1)
        if type(version) is not int or version != 1:
            raise ScenarioFormatError("only scenario schema_version 1 is supported")
        for field in ("id", "name"):
            if not isinstance(meta.get(field), str) or not meta[field].strip():
                raise ScenarioFormatError(f"scenario.{field} must be a non-empty string")
        description = meta.get("description", "")
        if not isinstance(description, str):
            raise ScenarioFormatError("scenario.description must be a string")
        if not isinstance(steps_raw, list) or not 1 <= len(steps_raw) <= 100:
            raise ScenarioFormatError("steps must contain between 1 and 100 operations")

        steps: list[ScenarioStep] = []
        names: set[str] = set()
        for index, item in enumerate(steps_raw, 1):
            if not isinstance(item, dict):
                raise ScenarioFormatError(f"step {index} must be a mapping")
            kind = item.get("type", "request")
            allowed = self.CONTROL_KEYS if kind == "control" else self.REQUEST_KEYS if kind == "request" else set()
            if not allowed or set(item) - allowed:
                raise ScenarioFormatError(f"step {index} contains unsupported fields or type")
            name = item.get("name")
            if not isinstance(name, str) or not name.strip() or name in names:
                raise ScenarioFormatError(f"step {index} requires a unique non-empty name")
            names.add(name)
            via = item.get("via")
            if not isinstance(via, str) or via not in {"origin", "proxy"}:
                raise ScenarioFormatError(f"step {index}: via must be origin or proxy")

            if kind == "control":
                operation = item.get("operation")
                if operation in {"grant", "revoke"}:
                    principal = item.get("principal")
                    if via != "origin" or not isinstance(principal, str) or not principal.strip() or "path" in item:
                        raise ScenarioFormatError(
                            f"step {index}: grant/revoke require origin and a principal; path is fixed"
                        )
                    path = None
                elif operation == "purge":
                    if via != "proxy" or "principal" in item:
                        raise ScenarioFormatError(f"step {index}: purge requires proxy and no principal")
                    path = self._path(item.get("path"), index)
                    principal = None
                else:
                    raise ScenarioFormatError(f"step {index}: unsupported control operation")
                expected = item.get("expect_status", 200)
                if type(expected) is not int or not 100 <= expected <= 599:
                    raise ScenarioFormatError(f"step {index}: expect_status must be an HTTP status")
                steps.append(ControlStep(name, operation, via, principal, path, expected))
                continue

            method, path = item.get("method", "GET"), self._path(item.get("path"), index)
            if not isinstance(method, str) or method not in {"GET", "HEAD"}:
                raise ScenarioFormatError(f"step {index}: only GET and HEAD are supported for requests")
            headers_raw = item.get("headers", {})
            if not isinstance(headers_raw, dict):
                raise ScenarioFormatError(f"step {index}: headers must be a mapping")
            headers: list[tuple[str, str]] = []
            for key, value in headers_raw.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    raise ScenarioFormatError(f"step {index}: header names and values must be strings")
                if key.lower() in {"host", "content-length", "transfer-encoding", "connection"}:
                    raise ScenarioFormatError(f"step {index}: forbidden request header {key!r}")
                if any(ord(char) < 32 and char != "\t" or ord(char) == 127 for char in key + value):
                    raise ScenarioFormatError(f"step {index}: control characters in headers are forbidden")
                headers.append((key, value))
            status = item.get("expect_status")
            if status is not None and (type(status) is not int or not 100 <= status <= 599):
                raise ScenarioFormatError(f"step {index}: expect_status must be an HTTP status")
            cache_state = item.get("expect_cache_state")
            if cache_state is not None and (
                not isinstance(cache_state, str) or cache_state not in self.CACHE_STATES
            ):
                raise ScenarioFormatError(f"step {index}: unsupported expected cache state")
            body_match = item.get("expect_body_contains")
            if body_match is not None and (not isinstance(body_match, str) or not body_match):
                raise ScenarioFormatError(f"step {index}: expect_body_contains must be non-empty text")
            steps.append(RequestStep(
                name=name, via=via, method=method, path=path,
                headers=tuple(headers), expected_status=status,
                expected_cache_state=cache_state, expected_body_contains=body_match,
            ))
        return ScenarioDefinition(
            scenario_id=meta["id"], name=meta["name"], description=description,
            steps=tuple(steps), schema_version=1,
        )
