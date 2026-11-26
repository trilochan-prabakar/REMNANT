"""Strict, versioned V3 scenario format for controlled HTTP cache experiments."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlsplit

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
class ScenarioDefinition:
    scenario_id: str
    name: str
    description: str
    steps: tuple[RequestStep, ...]
    schema_version: int = 1


class ScenarioLoader:
    """Load safe YAML scenario documents; URLs and executable code are not accepted."""

    ROOT_KEYS = {"scenario", "steps"}
    STEP_KEYS = {
        "name", "via", "method", "path", "headers",
        "expect_status", "expect_cache_state", "expect_body_contains",
    }
    CACHE_STATES = {"hit", "miss", "stale", "bypass", "unknown"}

    def loads(self, text: str) -> ScenarioDefinition:
        if not isinstance(text, str) or not text.strip():
            raise ScenarioFormatError("scenario document cannot be empty")
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ScenarioFormatError(f"invalid YAML: {exc}") from exc
        if not isinstance(raw, dict) or set(raw) != self.ROOT_KEYS:
            raise ScenarioFormatError("document must contain exactly 'scenario' and 'steps'")
        meta = raw["scenario"]
        steps_raw = raw["steps"]
        if not isinstance(meta, dict) or set(meta) - {"id", "name", "description", "schema_version"}:
            raise ScenarioFormatError("'scenario' must be a mapping with supported fields")
        if meta.get("schema_version", 1) != 1:
            raise ScenarioFormatError("only scenario schema_version 1 is supported")
        for field in ("id", "name"):
            if not isinstance(meta.get(field), str) or not meta[field].strip():
                raise ScenarioFormatError(f"scenario.{field} must be a non-empty string")
        description = meta.get("description", "")
        if not isinstance(description, str):
            raise ScenarioFormatError("scenario.description must be a string")
        if not isinstance(steps_raw, list) or not 1 <= len(steps_raw) <= 100:
            raise ScenarioFormatError("steps must contain between 1 and 100 requests")

        steps: list[RequestStep] = []
        names: set[str] = set()
        for index, item in enumerate(steps_raw, 1):
            if not isinstance(item, dict) or set(item) - self.STEP_KEYS:
                raise ScenarioFormatError(f"step {index} contains unsupported fields")
            name, via, method, path = (
                item.get("name"), item.get("via"), item.get("method", "GET"), item.get("path")
            )
            if not isinstance(name, str) or not name.strip() or name in names:
                raise ScenarioFormatError(f"step {index} requires a unique non-empty name")
            names.add(name)
            if via not in {"origin", "proxy"}:
                raise ScenarioFormatError(f"step {index}: via must be origin or proxy")
            if method not in {"GET", "HEAD"}:
                raise ScenarioFormatError(f"step {index}: only GET and HEAD are supported")
            if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
                raise ScenarioFormatError(f"step {index}: path must be an absolute-path reference")
            parsed = urlsplit(path)
            if parsed.scheme or parsed.netloc or "\\" in path:
                raise ScenarioFormatError(f"step {index}: absolute URLs and backslashes are forbidden")
            if any(part in {".", ".."} for part in parsed.path.split("/")):
                raise ScenarioFormatError(f"step {index}: path traversal is forbidden")
            headers_raw = item.get("headers", {})
            if not isinstance(headers_raw, dict):
                raise ScenarioFormatError(f"step {index}: headers must be a mapping")
            headers: list[tuple[str, str]] = []
            for key, value in headers_raw.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    raise ScenarioFormatError(f"step {index}: header names and values must be strings")
                if key.lower() in {"host", "content-length", "transfer-encoding", "connection"}:
                    raise ScenarioFormatError(f"step {index}: forbidden request header {key!r}")
                if "\r" in key or "\n" in key or "\r" in value or "\n" in value:
                    raise ScenarioFormatError(f"step {index}: header injection is forbidden")
                headers.append((key, value))
            status = item.get("expect_status")
            if status is not None and (type(status) is not int or not 100 <= status <= 599):
                raise ScenarioFormatError(f"step {index}: expect_status must be an HTTP status")
            cache_state = item.get("expect_cache_state")
            if cache_state is not None and cache_state not in self.CACHE_STATES:
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
