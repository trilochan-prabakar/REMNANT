"""Generate reproducible reports from persisted experiment evidence."""

import json
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

from remnant.storage import SQLiteEvidenceStore


_EXPECTED_STAGES = (
    "initial_authorization",
    "cache_prime",
    "permission_revocation",
    "origin_after_revocation",
    "cache_replay",
    "finding_oracle",
)
_FAILURE_OUTCOMES = {
    "initial_authorization": {"DENIED"},
    "cache_prime": {"NOT_PRIMED"},
    "permission_revocation": {"NOT_REVOKED"},
    "origin_after_revocation": {"ALLOWED_OR_OTHER"},
}


class ExperimentNotFoundError(LookupError):
    """Raised when a report is requested for an unknown experiment ID."""


class ReportGenerator:
    """Write JSON and standalone HTML reports from an evidence store."""

    def __init__(self, store: SQLiteEvidenceStore, output_dir: str | Path) -> None:
        self.store = store
        self.output_dir = Path(output_dir)

    def generate_json(self, experiment_id: str) -> Path:
        """Generate a JSON report and return its path."""
        report = self._report_for(experiment_id)
        output_path = self._output_path(experiment_id, ".json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return output_path

    def generate_html(self, experiment_id: str) -> Path:
        """Generate a standalone HTML report and return its path."""
        report = self._report_for(experiment_id)
        output_path = self._output_path(experiment_id, ".html")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self._render_html(report), encoding="utf-8")
        return output_path

    def _report_for(self, experiment_id: str) -> dict[str, Any]:
        saved = self.store.get_experiment(experiment_id)
        if saved is None:
            raise ExperimentNotFoundError(f"experiment not found: {experiment_id}")

        evidence_by_stage = {row["stage_type"]: row for row in saved["evidence"]}
        stages = [
            self._stage_record(stage_type, evidence_by_stage.get(stage_type))
            for stage_type in _EXPECTED_STAGES
        ]
        finding = saved.get("finding")
        oracle_evidence = evidence_by_stage.get("finding_oracle")
        oracle_details = self._details(oracle_evidence) if oracle_evidence else {}
        conditions = {
            "origin_denies": self._as_bool_or_none(
                finding.get("origin_denies") if finding else oracle_details.get("origin_denies")
            ),
            "cache_hit": self._as_bool_or_none(
                finding.get("cache_hit") if finding else oracle_details.get("cache_hit")
            ),
            "canary_matches": self._as_bool_or_none(
                finding.get("canary_match")
                if finding
                else oracle_details.get("canary_matches")
            ),
        }
        finding_status = (
            finding.get("confirmation_status")
            if finding
            else oracle_evidence.get("stage_outcome") if oracle_evidence else None
        )
        issues = self._issues(stages)
        if any(stage["status"] == "FAILED" for stage in stages):
            experiment_status = "FAILED"
        elif any(stage["status"] == "MISSING" for stage in stages):
            experiment_status = "INCOMPLETE"
        else:
            experiment_status = saved.get("overall_outcome", "INCOMPLETE")

        initial = evidence_by_stage.get("initial_authorization")
        prime = evidence_by_stage.get("cache_prime")
        revoke = evidence_by_stage.get("permission_revocation")
        origin = evidence_by_stage.get("origin_after_revocation")
        replay = evidence_by_stage.get("cache_replay")
        analysis = self._analysis_record(saved.get("analysis"))
        return {
            "report_schema_version": "2.0" if analysis is not None else "1.0",
            "experiment_status": experiment_status,
            "experiment": {
                "experiment_id": saved.get("experiment_id"),
                "principal_id": saved.get("principal_id"),
                "resource_id": saved.get("resource_id"),
                "started_at": saved.get("started_at"),
                "completed_at": saved.get("completed_at"),
            },
            "initial_authorization": self._compact_stage(initial),
            "cache_priming": self._compact_stage(prime),
            "permission_revocation": self._compact_stage(revoke),
            "origin_bypassed": self._compact_stage(origin),
            "normal_cache_request": self._compact_stage(replay),
            "canary_comparison": {
                "matches": self._as_bool_or_none(
                    replay.get("canary_match") if replay else None
                ),
                "cached_canary": (
                    self._details(prime).get("cached_canary") if prime else None
                ),
            },
            "oracle": {
                "conditions": conditions,
                "finding_confirmed": (
                    all(value is True for value in conditions.values())
                    if all(value is not None for value in conditions.values())
                    else None
                ),
            },
            "finding_status": finding_status,
            "analysis": analysis,
            "stages": stages,
            "issues": issues,
        }

    @staticmethod
    def _analysis_record(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        try:
            payload = json.loads(row.get("analysis_json", "{}"))
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        # Return only the versioned, allow-listed analysis object written by
        # SQLite. This keeps reports free of cache keys and response bodies.
        allowed = {
            "schema_version", "initial_origin_status",
            "cache_prime_observation_status", "cache_prime_metadata",
            "post_revocation_origin_status", "replay_observation_status",
            "replay_metadata", "differential", "diagnostic_categories",
        }
        if set(payload) != allowed:
            return None
        return payload

    @classmethod
    def _stage_record(cls, stage_type: str, row: dict[str, Any] | None) -> dict[str, Any]:
        if row is None:
            return {
                "stage_type": stage_type,
                "status": "MISSING",
                "stage_outcome": None,
                "timestamp": None,
                "http_status": None,
                "cache_status": None,
                "canary_match": None,
                "details": {},
            }
        outcome = row.get("stage_outcome")
        details = cls._details(row)
        outcome_text = str(outcome or "").upper()
        failed = (
            outcome_text in _FAILURE_OUTCOMES.get(stage_type, set())
            or outcome_text in {"FAILED", "ERROR"}
            or outcome_text.endswith("_FAILED")
            or bool(details.get("error") or details.get("errors"))
        )
        return {
            "stage_type": stage_type,
            "status": "FAILED" if failed else "SUCCESS",
            "stage_outcome": outcome,
            "timestamp": row.get("timestamp"),
            "http_status": row.get("http_status"),
            "cache_status": row.get("cache_status"),
            "canary_match": cls._as_bool_or_none(row.get("canary_match")),
            "details": details,
        }

    @staticmethod
    def _details(row: dict[str, Any] | None) -> dict[str, Any]:
        if row is None:
            return {}
        try:
            value = json.loads(row.get("details_json", "{}"))
        except (TypeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _as_bool_or_none(value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if value in (0, 1):
            return bool(value)
        return None

    @staticmethod
    def _compact_stage(row: dict[str, Any] | None) -> dict[str, Any]:
        if row is None:
            return {"status": "MISSING"}
        return {
            "status": "PRESENT",
            "stage_outcome": row.get("stage_outcome"),
            "http_status": row.get("http_status"),
            "cache_status": row.get("cache_status"),
            "canary_match": ReportGenerator._as_bool_or_none(row.get("canary_match")),
            "timestamp": row.get("timestamp"),
            "details": ReportGenerator._details(row),
        }

    @staticmethod
    def _issues(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        issues = []
        for stage in stages:
            stage_type = stage["stage_type"]
            if stage["status"] == "MISSING":
                issues.append({"type": "incomplete_stage", "stage_type": stage_type})
                continue
            if stage["status"] == "FAILED":
                issues.append(
                    {
                        "type": "failed_stage",
                        "stage_type": stage_type,
                        "stage_outcome": stage["stage_outcome"],
                    }
                )
            details = stage["details"]
            for key in ("error", "errors"):
                messages = details.get(key)
                if isinstance(messages, str):
                    messages = [messages]
                if isinstance(messages, list):
                    issues.extend(
                        {"type": "stage_error", "stage_type": stage_type, "message": str(message)}
                        for message in messages
                    )
            for key in ("warning", "warnings"):
                messages = details.get(key)
                if isinstance(messages, str):
                    messages = [messages]
                if isinstance(messages, list):
                    issues.extend(
                        {"type": "stage_warning", "stage_type": stage_type, "message": str(message)}
                        for message in messages
                    )
        return issues

    def _output_path(self, experiment_id: str, suffix: str) -> Path:
        # Percent-encoding prevents separators in an ID from escaping output_dir.
        filename = quote(experiment_id, safe="") + suffix
        return self.output_dir / filename

    @classmethod
    def _render_html(cls, report: dict[str, Any]) -> str:
        experiment = report["experiment"]
        finding = report.get("finding_status") or "INCOMPLETE"
        tone = {
            "CONFIRMED": "confirmed",
            "NOT_FOUND": "clear",
            "INCOMPLETE": "incomplete",
            "FAILED": "failed",
        }.get(finding, "neutral")
        report_status = report["experiment_status"]
        report_tone = {
            "FAILED": "failed",
            "INCOMPLETE": "incomplete",
            "COMPLETED": "clear",
        }.get(report_status, "neutral")
        summary_rows = (
            ("Experiment ID", experiment.get("experiment_id")),
            ("Principal", experiment.get("principal_id")),
            ("Resource", experiment.get("resource_id")),
            ("Started", experiment.get("started_at")),
            ("Completed", experiment.get("completed_at")),
        )
        summary = "".join(
            f"<div><span>{escape(label)}</span><strong>{cls._display(value)}</strong></div>"
            for label, value in summary_rows
        )
        stage_rows = "".join(
            "<tr>"
            f"<td>{escape(stage['stage_type'])}</td>"
            f"<td><span class=\"badge {stage['status'].lower()}\">{escape(stage['status'])}</span></td>"
            f"<td>{cls._display(stage['stage_outcome'])}</td>"
            f"<td>{cls._display(stage['http_status'])}</td>"
            f"<td>{cls._display(stage['cache_status'])}</td>"
            f"<td>{cls._display(stage['canary_match'])}</td>"
            f"<td>{cls._display(stage['timestamp'])}</td>"
            f"<td><code>{escape(json.dumps(stage['details'], ensure_ascii=False, sort_keys=True))}</code></td>"
            "</tr>"
            for stage in report["stages"]
        )
        conditions = report["oracle"]["conditions"]
        oracle_rows = "".join(
            f"<div><span>{escape(name.replace('_', ' ').title())}</span>"
            f"<strong class=\"condition {cls._condition_class(value)}\">{cls._display(value)}</strong></div>"
            for name, value in conditions.items()
        )
        analysis = report.get("analysis")
        if analysis is None:
            analysis_html = '<p class="muted">Analysis not recorded for this experiment.</p>'
        else:
            dimensions = analysis.get("differential", {})
            dimension_names = (
                ("status_code", "HTTP status"),
                ("selected_headers", "Selected headers"),
                ("body_digest", "Body digest"),
                ("canary", "Canary"),
            )
            dimension_rows = "".join(
                "<tr>"
                f"<td>{escape(label)}</td>"
                f"<td>{cls._display(dimensions.get(key, {}).get('state'))}</td>"
                "</tr>"
                for key, label in dimension_names
            )
            metadata_rows = "".join(
                "<tr>"
                f"<td>{escape(label)}</td>"
                f"<td>{cls._display(metadata.get(field))}</td>"
                "</tr>"
                for label, metadata in (
                    ("Cache prime", analysis.get("cache_prime_metadata", {})),
                    ("Cache replay", analysis.get("replay_metadata", {})),
                )
                for field, label in (
                    ("present", "Metadata present"),
                    ("valid", "Metadata valid"),
                    ("schema_version", "Metadata schema"),
                    ("principal_id", "Principal"),
                    ("resource_id", "Resource"),
                    ("tenant_id", "Tenant"),
                    ("response_status", "Response status"),
                    ("body_sha256", "Body SHA-256"),
                )
            )
            categories = analysis.get("diagnostic_categories", [])
            category_html = (
                ", ".join(escape(str(item)) for item in categories)
                if isinstance(categories, list) and categories
                else "None recorded"
            )
            analysis_html = (
                "<div class=\"summary\">"
                f"<div><span>Cache prime observation</span><strong>{cls._display(analysis.get('cache_prime_observation_status'))}</strong></div>"
                f"<div><span>Replay observation</span><strong>{cls._display(analysis.get('replay_observation_status'))}</strong></div>"
                f"<div><span>Differential state</span><strong>{cls._display(dimensions.get('state'))}</strong></div>"
                "</div>"
                "<h3>Differential dimensions</h3><div class=\"table-wrap\"><table>"
                "<thead><tr><th>Dimension</th><th>State</th></tr></thead>"
                f"<tbody>{dimension_rows}</tbody></table></div>"
                "<h3>Metadata validation</h3><div class=\"table-wrap\"><table>"
                "<thead><tr><th>Field</th><th>Value</th></tr></thead>"
                f"<tbody>{metadata_rows}</tbody></table></div>"
                f"<p>Diagnostic categories: {category_html}</p>"
            )
        issues = report["issues"]
        issue_html = (
            "<ul>" + "".join(
                "<li>"
                f"<b>{escape(issue['type'].replace('_', ' ').title())}</b>"
                f" — {escape(issue.get('stage_type', ''))}"
                f"{': ' + escape(issue['message']) if 'message' in issue else ''}"
                "</li>"
                for issue in issues
            ) + "</ul>"
            if issues
            else "<p class=\"muted\">No errors, warnings, or incomplete stages.</p>"
        )
        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>REMNANT Experiment Report</title>
<style>
:root {{ color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #07111f; color: #e5eef8; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: radial-gradient(ellipse at top right, #102b45 0, #07111f 48rem); min-height: 100vh; }}
main {{ max-width: 1180px; margin: 0 auto; padding: 2.25rem 1.25rem 4rem; }}
header {{ display: flex; justify-content: space-between; align-items: center; gap: 1rem; border-bottom: 1px solid #1c354d; padding-bottom: 1.4rem; }}
.brand {{ color: #39d8ed; font-size: .8rem; font-weight: 800; letter-spacing: .24em; }}
.status-pills {{ display: flex; flex-wrap: wrap; gap: .5rem; }}
h1 {{ font-size: clamp(1.65rem, 4vw, 2.5rem); margin: .45rem 0 0; }}
h2 {{ font-size: 1.1rem; margin: 0 0 1rem; }}
.pill, .badge {{ border: 1px solid #285069; border-radius: 999px; padding: .35rem .7rem; font-size: .72rem; font-weight: 800; letter-spacing: .06em; white-space: nowrap; }}
.confirmed, .success {{ color: #70f0c2; border-color: #24745e; background: #0c302b; }}
.clear {{ color: #9bd8ff; border-color: #28618a; background: #10283e; }}
.failed {{ color: #ff9b9b; border-color: #8d3a4d; background: #3b1724; }}
.incomplete {{ color: #ffd27b; border-color: #8d6b31; background: #392d16; }}
.neutral {{ color: #bdc9d5; }}
section {{ margin-top: 1.5rem; border: 1px solid #1a344b; border-radius: 14px; background: rgba(11, 27, 43, .88); padding: 1.25rem; box-shadow: 0 14px 34px rgba(0,0,0,.16); }}
.summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: .9rem; }}
.summary div, .oracle div {{ min-width: 0; display: grid; gap: .35rem; padding: .8rem; background: #0b1c2c; border: 1px solid #17374e; border-radius: 9px; }}
.summary span, .oracle span {{ font-size: .7rem; text-transform: uppercase; letter-spacing: .09em; color: #85a4bb; }}
.summary strong {{ overflow-wrap: anywhere; font-size: .88rem; }}
.overview {{ display: grid; grid-template-columns: 1fr 1.25fr; gap: 1.25rem; }}
.oracle {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: .7rem; }}
.condition.true {{ color: #70f0c2; }} .condition.false {{ color: #ffb56b; }} .condition.unknown {{ color: #ffd27b; }}
.timeline {{ display: grid; gap: .7rem; }}
.event {{ display: grid; grid-template-columns: 11rem 1fr; gap: 1rem; padding: .7rem .85rem; border-left: 2px solid #24bed4; background: #0b1c2c; border-radius: 0 8px 8px 0; }}
.event b {{ color: #9ebbd0; font-size: .8rem; }} .event span {{ font-size: .82rem; overflow-wrap: anywhere; }}
.table-wrap {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: .78rem; }}
th {{ color: #75cde0; text-align: left; text-transform: uppercase; letter-spacing: .06em; font-size: .67rem; }}
th, td {{ border-bottom: 1px solid #1a344b; padding: .7rem .55rem; vertical-align: top; }}
td code {{ white-space: pre-wrap; overflow-wrap: anywhere; color: #acc6d9; font-size: .7rem; }}
.muted {{ color: #91a8bb; margin: 0; }} ul {{ margin: 0; padding-left: 1.2rem; }} li {{ margin: .45rem 0; color: #d9e5ee; }}
@media (max-width: 760px) {{ .overview {{ grid-template-columns: 1fr; }} header {{ align-items: flex-start; flex-direction: column; }} .event {{ grid-template-columns: 1fr; gap: .35rem; }} .oracle {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body><main>
<header><div><div class="brand">REMNANT / SECURITY VALIDATION</div><h1>Experiment Report</h1></div>
<div class="status-pills"><span class="pill {tone}">Finding {escape(str(finding))}</span>
<span class="pill {report_tone}">{escape(report_status)}</span></div></header>
<section><h2>Experiment summary</h2><div class="summary">{summary}</div></section>
<div class="overview">
<section><h2>Finding oracle</h2><div class="oracle">{oracle_rows}</div>
<p style="margin:1rem 0 0">Persisted finding: <strong>{escape(str(finding))}</strong></p>
<p style="margin:.5rem 0 0">Oracle confirmation: <strong>{cls._display(report['oracle']['finding_confirmed'])}</strong></p></section>
<section><h2>Experiment timeline</h2><div class="timeline">{cls._timeline(report['stages'])}</div></section>
</div>
<section><h2>V2 analysis evidence</h2>{analysis_html}</section>
<section><h2>Detailed stage evidence</h2><div class="table-wrap"><table><thead><tr><th>Stage</th><th>Status</th><th>Outcome</th><th>HTTP</th><th>Cache</th><th>Canary</th><th>Timestamp</th><th>Details</th></tr></thead><tbody>{stage_rows}</tbody></table></div></section>
<section><h2>Errors, warnings, and incomplete stages</h2>{issue_html}</section>
<footer style="margin-top:1rem;color:#6f8ba1;font-size:.72rem">Report schema {escape(report['report_schema_version'])} · Experiment status {escape(report['experiment_status'])}</footer>
</main></body></html>
"""

    @staticmethod
    def _display(value: Any) -> str:
        if value is None:
            return '<span class="muted">Not recorded</span>'
        return escape("true" if value is True else "false" if value is False else str(value))

    @staticmethod
    def _condition_class(value: bool | None) -> str:
        return "true" if value is True else "false" if value is False else "unknown"

    @classmethod
    def _timeline(cls, stages: list[dict[str, Any]]) -> str:
        return "".join(
            "<div class=\"event\">"
            f"<b>{escape(stage['stage_type'].replace('_', ' ').title())}</b>"
            f"<span>{cls._display(stage['stage_outcome'])} · {cls._display(stage['timestamp'])}</span>"
            "</div>"
            for stage in stages
        )
