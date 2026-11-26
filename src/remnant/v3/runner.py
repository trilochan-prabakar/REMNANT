"""Bounded HTTP scenario runner with redacted, body-free evidence."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import httpx

from remnant.v3.cache_analysis import CacheAnalysis, analyze_response
from remnant.v3.scenarios import ScenarioDefinition


class RunStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


@dataclass(frozen=True)
class RequestTrace:
    step_name: str
    via: str
    method: str
    path: str
    status_code: int | None
    elapsed_ms: float | None
    response_headers: tuple[tuple[str, str], ...]
    body_sha256: str | None
    body_bytes: int
    body_truncated: bool
    cache_analysis: dict[str, Any] | None
    assertion_results: tuple[tuple[str, bool], ...]
    error: str | None = None


@dataclass(frozen=True)
class ScenarioRun:
    run_id: str
    scenario_id: str
    scenario_name: str
    started_at: str
    completed_at: str
    status: RunStatus
    traces: tuple[RequestTrace, ...]


_SENSITIVE_HEADER = re.compile(r"authorization|cookie|token|secret|api[-_]key|session", re.I)
_SAFE_RESPONSE_HEADERS = {
    "cache-control", "expires", "date", "age", "vary", "cache-status",
    "x-cache", "x-cache-status", "cf-cache-status", "x-proxy-cache",
    "content-type", "content-length", "etag", "last-modified", "warning",
}


def _redact_path(path: str) -> str:
    """Redact secret-like query values before a request path enters evidence."""
    parsed = urlsplit(path)
    safe_query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if _SENSITIVE_HEADER.search(key):
            value = "[REDACTED]"
        safe_query.append((key, value))
    return urlunsplit(("", "", parsed.path, urlencode(safe_query), ""))


def _redact_headers(headers: httpx.Headers) -> tuple[tuple[str, str], ...]:
    safe = []
    for key, value in headers.multi_items():
        lower = key.lower()
        if _SENSITIVE_HEADER.search(lower):
            continue
        if lower in _SAFE_RESPONSE_HEADERS:
            safe.append((lower, value[:512]))
    return tuple(safe)


class ScenarioRunner:
    """Execute a scenario using separately configured origin and proxy clients.

    Clients are injected by the caller, making target selection explicit. This
    runner does not crawl, follow redirects, mutate application state, or accept
    arbitrary URLs from scenario documents.
    """

    def __init__(
        self,
        *,
        origin_client: httpx.AsyncClient,
        proxy_client: httpx.AsyncClient,
        max_response_bytes: int = 1_048_576,
        timeout_seconds: float = 10.0,
    ) -> None:
        if type(max_response_bytes) is not int or not 1 <= max_response_bytes <= 10_485_760:
            raise ValueError("max_response_bytes must be between 1 and 10 MiB")
        if not isinstance(timeout_seconds, (int, float)) or not 0.1 <= timeout_seconds <= 60:
            raise ValueError("timeout_seconds must be between 0.1 and 60")
        for label, client in (("origin_client", origin_client), ("proxy_client", proxy_client)):
            if not isinstance(client, httpx.AsyncClient):
                raise TypeError(f"{label} must be an httpx.AsyncClient")
            if client.base_url.scheme not in {"http", "https"}:
                raise ValueError(f"{label} must use HTTP or HTTPS")
        self.origin_client = origin_client
        self.proxy_client = proxy_client
        self.max_response_bytes = max_response_bytes
        self.timeout_seconds = float(timeout_seconds)

    async def run(self, scenario: ScenarioDefinition) -> ScenarioRun:
        if not isinstance(scenario, ScenarioDefinition):
            raise TypeError("scenario must be a ScenarioDefinition")
        run_id = uuid4().hex
        started = datetime.now(timezone.utc).isoformat()
        traces: list[RequestTrace] = []
        failed = False
        had_error = False
        for step in scenario.steps:
            client = self.origin_client if step.via == "origin" else self.proxy_client
            try:
                trace = await self._request(step, client)
            except (httpx.HTTPError, TimeoutError, OSError) as exc:
                had_error = True
                traces.append(RequestTrace(
                    step_name=step.name, via=step.via, method=step.method, path=_redact_path(step.path),
                    status_code=None, elapsed_ms=None, response_headers=(),
                    body_sha256=None, body_bytes=0, body_truncated=False,
                    cache_analysis=None, assertion_results=(),
                    error=f"{type(exc).__name__}: request failed; details omitted to avoid leaking URL data",
                ))
                # Stop: later assertions may depend on a response that did not arrive.
                break
            traces.append(trace)
            failed = failed or any(not passed for _, passed in trace.assertion_results)
        completed = datetime.now(timezone.utc).isoformat()
        status = RunStatus.ERROR if had_error else RunStatus.FAILED if failed else RunStatus.PASSED
        return ScenarioRun(
            run_id=run_id, scenario_id=scenario.scenario_id, scenario_name=scenario.name,
            started_at=started, completed_at=completed, status=status, traces=tuple(traces),
        )

    async def _request(self, step, client: httpx.AsyncClient) -> RequestTrace:
        started = datetime.now(timezone.utc)
        async with client.stream(
            step.method, step.path, headers=dict(step.headers),
            timeout=self.timeout_seconds, follow_redirects=False,
        ) as response:
            chunks: list[bytes] = []
            total = 0
            truncated = False
            async for chunk in response.aiter_bytes():
                remaining = self.max_response_bytes - total
                if remaining <= 0:
                    truncated = True
                    break
                accepted = chunk[:remaining]
                chunks.append(accepted)
                total += len(accepted)
                if len(accepted) < len(chunk):
                    truncated = True
                    break
            body = b"".join(chunks)
            elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000
            headers = response.headers
            analysis = analyze_response(
                response.status_code, dict(headers),
                request_had_authorization=any(k.lower() == "authorization" for k, _ in step.headers),
            )
            body_text = body.decode("utf-8", errors="replace")
            assertions: list[tuple[str, bool]] = []
            if step.expected_status is not None:
                assertions.append((f"status == {step.expected_status}", response.status_code == step.expected_status))
            if step.expected_cache_state is not None:
                assertions.append((f"cache_state == {step.expected_cache_state}", analysis.cache_state.value == step.expected_cache_state))
            if step.expected_body_contains is not None:
                assertions.append(("expected body marker present", step.expected_body_contains in body_text))
            return RequestTrace(
                step_name=step.name, via=step.via, method=step.method, path=_redact_path(step.path),
                status_code=response.status_code, elapsed_ms=round(elapsed, 3),
                response_headers=_redact_headers(headers),
                body_sha256=hashlib.sha256(body).hexdigest(), body_bytes=total,
                body_truncated=truncated, cache_analysis=asdict(analysis),
                assertion_results=tuple(assertions),
            )


def run_to_dict(run: ScenarioRun) -> dict[str, Any]:
    """Return JSON-safe evidence; response bodies and request secrets are never stored."""
    data = asdict(run)
    data["status"] = run.status.value
    return data


def run_to_json(run: ScenarioRun, *, indent: int = 2) -> str:
    return json.dumps(run_to_dict(run), indent=indent, sort_keys=True)
