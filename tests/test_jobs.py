from datetime import datetime, timedelta, timezone

import pytest

from infrastructure.job_queue import JobQueue, JobQueueError, process_one, register_job_handler


def test_jobs_are_idempotent_and_tenant_scoped(tmp_path):
    queue = JobQueue(str(tmp_path / "jobs.db"))
    first = queue.enqueue("acme", "connector.sync", {"source": "crm"}, idempotency_key="sync-1")
    duplicate = queue.enqueue("acme", "connector.sync", {"source": "changed"}, idempotency_key="sync-1")
    other = queue.enqueue("other", "connector.sync", {"source": "crm"}, idempotency_key="sync-1")

    assert duplicate["duplicate"] is True
    assert duplicate["id"] == first["id"]
    assert other["id"] != first["id"]
    with pytest.raises(JobQueueError):
        queue.get("other", first["id"])


def test_failed_jobs_retry_with_backoff_then_dead_letter(tmp_path):
    queue = JobQueue(str(tmp_path / "jobs.db"))
    job = queue.enqueue("acme", "always.fail", {}, max_attempts=2)

    claimed = queue.claim("worker-1")
    retried = queue.fail(claimed["id"], "worker-1", "provider unavailable", base_delay_seconds=1)
    assert retried["status"] == "retry"

    conn = queue._connect()
    conn.execute("UPDATE durable_jobs SET available_at=? WHERE id=?", ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), job["id"]))
    conn.commit()
    conn.close()

    claimed_again = queue.claim("worker-2")
    dead = queue.fail(claimed_again["id"], "worker-2", "provider unavailable", base_delay_seconds=1)
    assert dead["status"] == "dead_letter"
    assert dead["attempts"] == 2
    assert queue.stats("acme")["dead_letter"] == 1


@pytest.mark.asyncio
async def test_registered_handler_completes_a_job(tmp_path):
    queue = JobQueue(str(tmp_path / "jobs.db"))

    async def handler(job):
        return {"record_count": len(job["payload"]["records"])}

    register_job_handler("records.import", handler)
    queued = queue.enqueue("acme", "records.import", {"records": [{"id": 1}, {"id": 2}]})
    processed = await process_one(queue, "worker-test")

    assert processed["status"] == "completed"
    assert queue.get("acme", queued["id"])["result"]["record_count"] == 2


def test_worker_heartbeats_report_only_live_workers(tmp_path):
    queue = JobQueue(str(tmp_path / "jobs.db"))
    heartbeat = queue.heartbeat("worker-api")

    status = queue.worker_status(max_age_seconds=10)

    assert heartbeat["worker_id"] == "worker-api"
    assert status["status"] == "ready"
    assert status["active_count"] == 1
    assert status["workers"][0]["worker_id"] == "worker-api"
