"""SQLite persistence for completed cache replay experiments."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from remnant.engine.experiment import ExperimentResult


_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    overall_outcome TEXT NOT NULL CHECK (overall_outcome IN ('COMPLETED')),
    finding_status TEXT NOT NULL CHECK (finding_status IN ('CONFIRMED', 'NOT_FOUND'))
);

CREATE TABLE IF NOT EXISTS experiment_evidence (
    evidence_id INTEGER PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    stage_type TEXT NOT NULL,
    stage_outcome TEXT NOT NULL,
    http_status INTEGER,
    cache_status TEXT CHECK (cache_status IS NULL OR cache_status IN ('HIT', 'MISS')),
    canary_match INTEGER CHECK (canary_match IS NULL OR canary_match IN (0, 1)),
    timestamp TEXT NOT NULL,
    details_json TEXT NOT NULL CHECK (json_valid(details_json))
);

CREATE TABLE IF NOT EXISTS findings (
    experiment_id TEXT PRIMARY KEY REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    classification TEXT NOT NULL,
    origin_denies INTEGER NOT NULL CHECK (origin_denies IN (0, 1)),
    cache_hit INTEGER NOT NULL CHECK (cache_hit IN (0, 1)),
    canary_match INTEGER NOT NULL CHECK (canary_match IN (0, 1)),
    confirmation_status TEXT NOT NULL CHECK (confirmation_status IN ('CONFIRMED', 'NOT_FOUND')),
    CHECK ((confirmation_status = 'CONFIRMED') =
           (origin_denies = 1 AND cache_hit = 1 AND canary_match = 1))
);

CREATE INDEX IF NOT EXISTS idx_experiments_principal_resource
    ON experiments(principal_id, resource_id);
CREATE INDEX IF NOT EXISTS idx_experiments_completed_at
    ON experiments(completed_at);
CREATE INDEX IF NOT EXISTS idx_evidence_experiment_stage
    ON experiment_evidence(experiment_id, stage_type);
CREATE INDEX IF NOT EXISTS idx_findings_confirmation_status
    ON findings(confirmation_status);
"""


class SQLiteEvidenceStore:
    """Save and query completed experiment results in a configurable SQLite file."""

    def __init__(self, database_path: str | Path) -> None:
        configured_path = str(database_path)
        if not configured_path:
            raise ValueError("database_path must not be empty")
        if configured_path == ":memory:":
            self.database_path = f"file:remnant-{uuid4().hex}?mode=memory&cache=shared"
            self._uri = True
            self._memory_keeper = sqlite3.connect(self.database_path, uri=True)
            self._memory_keeper.execute("PRAGMA foreign_keys = ON")
        else:
            path = Path(configured_path).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            self.database_path = str(path)
            self._uri = False
            self._memory_keeper = None
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5.0, uri=self._uri)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        """Create tables and indexes; safe to call more than once."""
        connection = self._connect()
        try:
            with connection:
                connection.executescript(_SCHEMA)
        finally:
            connection.close()

    def save_experiment(self, result: ExperimentResult) -> None:
        """Persist the result, its derived stage evidence, and its finding atomically."""
        confirmed = (
            result.oracle_origin_denies
            and result.oracle_cache_hit
            and result.oracle_canary_matches
        )
        expected_finding_status = "CONFIRMED" if confirmed else "NOT_FOUND"
        if result.finding_status != expected_finding_status:
            raise ValueError("finding_status must match the finding oracle conditions")

        now = datetime.now(timezone.utc).isoformat()
        started_at = result.started_at or now
        completed_at = result.completed_at or now
        evidence_timestamp = completed_at
        evidence = self._evidence_rows(result, evidence_timestamp)
        finding_status = result.finding_status

        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    """INSERT INTO experiments
                       (experiment_id, principal_id, resource_id, started_at,
                        completed_at, overall_outcome, finding_status)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        result.experiment_id,
                        result.principal_id,
                        result.resource_id,
                        started_at,
                        completed_at,
                        "COMPLETED",
                        finding_status,
                    ),
                )
                connection.executemany(
                    """INSERT INTO experiment_evidence
                       (experiment_id, stage_type, stage_outcome, http_status,
                        cache_status, canary_match, timestamp, details_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (
                            result.experiment_id,
                            stage_type,
                            outcome,
                            http_status,
                            cache_status,
                            canary_match,
                            timestamp,
                            json.dumps(details, separators=(",", ":"), sort_keys=True),
                        )
                        for (
                            stage_type,
                            outcome,
                            http_status,
                            cache_status,
                            canary_match,
                            timestamp,
                            details,
                        ) in evidence
                    ],
                )
                connection.execute(
                    """INSERT INTO findings
                       (experiment_id, classification, origin_denies, cache_hit,
                        canary_match, confirmation_status)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        result.experiment_id,
                        "CACHE_AUTHORIZATION_INCONSISTENCY",
                        int(result.oracle_origin_denies),
                        int(result.oracle_cache_hit),
                        int(result.oracle_canary_matches),
                        finding_status,
                    ),
                )
        finally:
            connection.close()

    def get_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        """Return one experiment with its evidence and finding, or ``None``."""
        connection = self._connect()
        try:
            experiment = connection.execute(
                "SELECT * FROM experiments WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()
            if experiment is None:
                return None
            evidence = connection.execute(
                """SELECT * FROM experiment_evidence
                   WHERE experiment_id = ? ORDER BY evidence_id""",
                (experiment_id,),
            ).fetchall()
            finding = connection.execute(
                "SELECT * FROM findings WHERE experiment_id = ?", (experiment_id,)
            ).fetchone()
            return {
                **dict(experiment),
                "evidence": [dict(row) for row in evidence],
                "finding": dict(finding) if finding is not None else None,
            }
        finally:
            connection.close()

    def list_experiments(self) -> list[dict[str, Any]]:
        """List experiment summaries ordered by start time and ID."""
        connection = self._connect()
        try:
            rows = connection.execute(
                """SELECT * FROM experiments
                   ORDER BY started_at, experiment_id"""
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()

    def get_confirmed_findings(self) -> list[dict[str, Any]]:
        """Return confirmed findings with their experiment identity and context."""
        connection = self._connect()
        try:
            rows = connection.execute(
                """SELECT f.*, e.principal_id, e.resource_id, e.started_at, e.completed_at
                   FROM findings AS f
                   JOIN experiments AS e USING (experiment_id)
                   WHERE f.confirmation_status = ?
                   ORDER BY e.completed_at, f.experiment_id""",
                ("CONFIRMED",),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()

    @staticmethod
    def _evidence_rows(
        result: ExperimentResult, timestamp: str
    ) -> list[tuple[str, str, int | None, str | None, int | None, str, dict[str, Any]]]:
        cache_prime_status = getattr(result.cache_prime_status, "value", result.cache_prime_status)
        cache_status = getattr(result.cache_status, "value", result.cache_status)
        return [
            (
                "initial_authorization",
                "AUTHORIZED" if result.initial_authorization_status == 200 else "DENIED",
                result.initial_authorization_status,
                None,
                None,
                timestamp,
                {"principal_id": result.principal_id, "resource_id": result.resource_id},
            ),
            (
                "cache_prime",
                "PRIMED" if result.cache_primed else "NOT_PRIMED",
                None,
                str(cache_prime_status),
                None,
                timestamp,
                {"cached_canary": result.cached_canary},
            ),
            (
                "permission_revocation",
                "REVOKED" if result.permission_revoked else "NOT_REVOKED",
                None,
                None,
                None,
                timestamp,
                {"permission_revoked": result.permission_revoked},
            ),
            (
                "origin_after_revocation",
                "DENIED" if result.oracle_origin_denies else "ALLOWED_OR_OTHER",
                result.origin_status_after_revocation,
                None,
                None,
                timestamp,
                {"origin_denies": result.oracle_origin_denies},
            ),
            (
                "cache_replay",
                "HIT" if result.oracle_cache_hit else "MISS",
                None,
                str(cache_status),
                int(result.oracle_canary_matches),
                timestamp,
                {"canary_match": result.canary_match},
            ),
            (
                "finding_oracle",
                result.finding_status,
                result.origin_status_after_revocation,
                str(cache_status),
                int(result.oracle_canary_matches),
                timestamp,
                {
                    "origin_denies": result.oracle_origin_denies,
                    "cache_hit": result.oracle_cache_hit,
                    "canary_matches": result.oracle_canary_matches,
                    "finding_confirmed": result.finding_status == "CONFIRMED",
                },
            ),
        ]
