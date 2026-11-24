# SQLite Evidence Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist completed `ExperimentResult` values, derived stage evidence, and final oracle findings in SQLite.

**Architecture:** Add a dedicated `SQLiteEvidenceStore` using Python's built-in `sqlite3`. Store experiment metadata, evidence stages, and finding conditions in relational tables; reconstruct a structured result from the existing result dataclass without changing the experiment engine or oracle.

**Tech Stack:** Python 3.12, `sqlite3`, JSON text, pytest with temporary database files.

**Spec:** `Rem_Ins_8.txt`

## Global Constraints

- Use sqlite3 only; add no ORM or dependency.
- Keep the experiment engine and finding oracle unchanged.
- Keep execution functional when no database is configured.
- Use parameterized SQL, foreign keys, transactions with rollback, and JSON text for structured evidence.
- Do not store credentials or secrets; do not add reporting, dashboards, or later phase features.
- Preserve all pre-existing untracked files and project databases.

## Review Focus

- Evidence write failure must roll back the experiment and finding rows.
- Invalid or untrusted structured details must not become executable SQL.
- Foreign key enforcement must work on every opened connection.
- Persisted enums, nullable evidence fields, and timestamps must round-trip predictably.
- Default experiment construction must not require a database.

---

### Task 1: SQLite schema, serialization, and read/write API

**Files:**
- Create: `src/remnant/storage/__init__.py`
- Create: `src/remnant/storage/sqlite.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: `remnant.engine.experiment.ExperimentResult` and `remnant.cache.manager.CacheStatus`.
- Produces: `SQLiteEvidenceStore(database_path)`, `initialize()`, `save_experiment(result)`, `get_experiment(experiment_id)`, `list_experiments()`, and `get_confirmed_findings()`.

- [ ] Write tests for schema initialization, successful and non-finding saves, retrieval/listing, findings, foreign keys, rollback, connection persistence, timestamps, and structured JSON evidence.
- [ ] Run focused tests and confirm they fail because the storage API is missing.
- [ ] Implement schema and store API with transaction-scoped parameterized statements and per-connection foreign-key enforcement.
- [ ] Run focused tests and confirm all storage behaviors pass.

### Task 2: Full project verification and real Redis experiment

**Files:**
- Modify: none beyond Task 1 files.

- [ ] Run the complete pytest suite and record exact pass/fail/skip counts.
- [ ] Demonstrate saving/retrieving a completed experiment from separate SQLite connections.
- [ ] Run the existing end-to-end Redis integration test and record whether it ran or skipped due to Redis availability.
- [ ] Review the final diff and report all files created or modified.
