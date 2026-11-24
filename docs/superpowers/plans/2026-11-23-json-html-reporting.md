# JSON and HTML Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate reproducible JSON and standalone HTML reports from SQLite experiment evidence.

**Architecture:** A report generator reads `SQLiteEvidenceStore.get_experiment`, normalizes persisted metadata, evidence stages, and oracle values into a deterministic report mapping, then serializes that mapping as JSON or escaped standalone HTML. Generation methods write to a caller-selected output directory and return the resulting path.

**Tech Stack:** Python 3.12, sqlite3-backed existing store, stdlib json/html/pathlib, pytest.

**Spec:** `Rem_Ins_9.txt`

## Global Constraints

- Reuse existing SQLite storage and experiment structures; do not redesign them.
- Do not modify the finding oracle, experiment engine, or Redis behavior.
- Reports must be generated from persisted evidence and must not invent missing evidence.
- HTML must be standalone, use inline CSS only, and escape all untrusted text.
- Do not add AI/ML, dashboards, or V2/V3 features.
- Preserve existing untracked files and changes; do not reset or switch branches.

## Review Focus

- Unknown experiment IDs raise a clear reporting exception and create no output.
- Missing/failed evidence is represented distinctly from successful evidence.
- Malformed persisted details do not crash report generation or create injected HTML.
- Output filenames cannot escape the chosen output directory through experiment IDs.
- Both renderers preserve all three oracle conditions and their booleans.

---

### Task 1: Persisted JSON and HTML report generation

**Files:**
- Modify: `src/remnant/reporting/__init__.py`
- Create: `src/remnant/reporting/reports.py`
- Test: `tests/test_reporting.py`

**Interfaces:**
- Consumes: `SQLiteEvidenceStore.get_experiment(experiment_id)`.
- Produces: `ReportGenerator(store, output_dir).generate_json(experiment_id) -> Path`, `.generate_html(experiment_id) -> Path`, and `ExperimentNotFoundError`.

- [ ] Write failing tests for confirmed and non-finding JSON, timestamps/booleans/oracle conditions, persisted HTML and escaping, standalone output, unknown IDs, partial/failed stages, and output paths.
- [ ] Run `pytest tests/test_reporting.py -q` and confirm failures are due to the reporting API being absent.
- [ ] Implement one normalized report structure from stored evidence; represent each known stage as SUCCESS, FAILED, INCOMPLETE, or MISSING; write deterministic JSON and responsive standalone HTML with escaped values.
- [ ] Run `pytest tests/test_reporting.py -q` and confirm all reporting tests pass.
- [ ] Run the complete `pytest -q` suite.
- [ ] Save one confirmed experiment to SQLite, generate both reports under `reports/`, and inspect the reports for finding/oracle correctness, valid JSON, standalone HTML, and expected paths.
