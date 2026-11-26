"""Run the REMNANT demonstration against the Docker Compose Redis service."""

import json
from pathlib import Path
from uuid import uuid4

from redis import Redis

from remnant.cache.manager import RedisCacheManager
from remnant.engine.experiment import CacheReplayExperiment
from remnant.reporting import ReportGenerator
from remnant.storage import SQLiteEvidenceStore


def main() -> None:
    output_dir = Path("reports/generated")
    output_dir.mkdir(parents=True, exist_ok=True)
    client = Redis.from_url(
        "redis://redis:6379/0",
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    try:
        client.ping()
        cache = RedisCacheManager(
            client=client,
            key_prefix=f"remnant:compose-demo:{uuid4().hex}:",
        )
        result = CacheReplayExperiment(cache=cache).run(
            "alice", "document-1", ttl_seconds=60
        )
        if result.finding_status != "CONFIRMED":
            raise RuntimeError(
                f"Expected CONFIRMED for the controlled demo, got {result.finding_status}"
            )

        store = SQLiteEvidenceStore("reports/evidence.sqlite3")
        store.save_experiment(result)
        saved = store.get_experiment(result.experiment_id)
        if saved is None or len(saved["evidence"]) != 6:
            raise RuntimeError("Expected six persisted evidence stages")

        generator = ReportGenerator(store, output_dir)
        json_path = generator.generate_json(result.experiment_id)
        html_path = generator.generate_html(result.experiment_id)
        report = json.loads(json_path.read_text(encoding="utf-8"))
        if report["finding_status"] != "CONFIRMED" or not html_path.is_file():
            raise RuntimeError("Generated report validation failed")

        print(f"Experiment: {result.experiment_id}")
        print(f"Finding: {result.finding_status}")
        print(f"Evidence stages: {len(saved['evidence'])}")
        print(f"JSON report: {json_path}")
        print(f"HTML report: {html_path}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
