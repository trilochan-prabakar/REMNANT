"""Independent V3 SQLite evidence store and deterministic run comparison."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from remnant.v3.runner import ScenarioRun, run_to_dict


@dataclass(frozen=True)
class StepDifference:
    step_name: str
    changed_fields: tuple[str, ...]
    before: dict[str, Any]
    after: dict[str, Any]


@dataclass(frozen=True)
class RunComparison:
    before_run_id: str
    after_run_id: str
    status_changed: bool
    before_status: str
    after_status: str
    added_steps: tuple[str, ...]
    removed_steps: tuple[str, ...]
    changed_steps: tuple[StepDifference, ...]


class V3EvidenceStore:
    """Persist body-free V3 run records without changing the V2 evidence schema."""

    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > self.SCHEMA_VERSION:
                raise RuntimeError(
                    f"V3 evidence schema {version} is newer than supported "
                    f"schema {self.SCHEMA_VERSION}"
                )
            if version == 0:
                connection.executescript(
                    """
                    CREATE TABLE v3_runs (
                        run_id TEXT PRIMARY KEY,
                        scenario_id TEXT NOT NULL,
                        scenario_name TEXT NOT NULL,
                        started_at TEXT NOT NULL,
                        completed_at TEXT NOT NULL,
                        status TEXT NOT NULL CHECK(status IN ('passed', 'failed', 'error')),
                        payload_json TEXT NOT NULL
                    );
                    CREATE INDEX idx_v3_runs_scenario
                        ON v3_runs(scenario_id, completed_at);
                    PRAGMA user_version = 1;
                    """
                )
                connection.commit()

    def save(self, run: ScenarioRun) -> None:
        if not isinstance(run, ScenarioRun):
            raise TypeError("run must be a ScenarioRun")
        payload = json.dumps(run_to_dict(run), sort_keys=True, separators=(",", ":"))
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO v3_runs
                    (run_id, scenario_id, scenario_name, started_at, completed_at, status, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id, run.scenario_id, run.scenario_name, run.started_at,
                    run.completed_at, run.status.value, payload,
                ),
            )
            connection.commit()

    def get(self, run_id: str) -> dict[str, Any] | None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT payload_json FROM v3_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list_runs(self, *, scenario_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        with closing(self._connect()) as connection:
            if scenario_id is None:
                rows = connection.execute(
                    "SELECT payload_json FROM v3_runs ORDER BY completed_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT payload_json FROM v3_runs WHERE scenario_id = ? "
                    "ORDER BY completed_at DESC LIMIT ?",
                    (scenario_id, limit),
                ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def compare(self, before_run_id: str, after_run_id: str) -> RunComparison:
        before = self.get(before_run_id)
        after = self.get(after_run_id)
        if before is None or after is None:
            missing = before_run_id if before is None else after_run_id
            raise KeyError(f"V3 run not found: {missing}")
        if before["scenario_id"] != after["scenario_id"]:
            raise ValueError("runs must belong to the same scenario_id")

        old_steps = {item["step_name"]: item for item in before["traces"]}
        new_steps = {item["step_name"]: item for item in after["traces"]}
        added = tuple(sorted(new_steps.keys() - old_steps.keys()))
        removed = tuple(sorted(old_steps.keys() - new_steps.keys()))
        fields = (
            "via", "method", "path", "status_code", "body_sha256",
            "body_bytes", "body_truncated", "cache_analysis", "assertion_results", "error",
        )
        changes: list[StepDifference] = []
        for name in sorted(old_steps.keys() & new_steps.keys()):
            old = old_steps[name]
            new = new_steps[name]
            changed = tuple(field for field in fields if old.get(field) != new.get(field))
            if changed:
                changes.append(StepDifference(
                    step_name=name,
                    changed_fields=changed,
                    before={field: old.get(field) for field in changed},
                    after={field: new.get(field) for field in changed},
                ))
        return RunComparison(
            before_run_id=before_run_id,
            after_run_id=after_run_id,
            status_changed=before["status"] != after["status"],
            before_status=before["status"],
            after_status=after["status"],
            added_steps=added,
            removed_steps=removed,
            changed_steps=tuple(changes),
        )
