from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import redis

from shared.models import ScrapeJob, ScrapeTask, WorkerInfo, WorkerStatus

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class TaskQueue:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = redis.from_url(redis_url, decode_responses=True)

    # --- Task queue methods ---
    def push_task(self, task: ScrapeTask) -> None:
        try:
            self.redis.lpush("queue:pending", task.model_dump_json())
        except redis.RedisError:
            logger.exception("Failed to push task to queue")

    def pop_task(self, timeout: int = 5) -> Optional[ScrapeTask]:
        try:
            item = self.redis.brpop("queue:pending", timeout=timeout)
            if not item:
                return None
            _key, raw = item
            return ScrapeTask.model_validate_json(raw)
        except redis.RedisError:
            logger.exception("Failed to pop task from queue")
            return None
        except Exception:
            logger.exception("Failed to deserialize task from queue")
            return None

    def get_queue_length(self) -> int:
        try:
            return int(self.redis.llen("queue:pending"))
        except redis.RedisError:
            logger.exception("Failed to get queue length")
            return 0

    # --- State persistence methods ---
    def save_task(self, task: ScrapeTask) -> None:
        try:
            self.redis.set(f"task:{task.id}", task.model_dump_json(), ex=86400)
        except redis.RedisError:
            logger.exception("Failed to save task %s", task.id)

    def get_task(self, task_id: str) -> Optional[ScrapeTask]:
        try:
            raw = self.redis.get(f"task:{task_id}")
            if raw is None:
                return None
            return ScrapeTask.model_validate_json(raw)
        except redis.RedisError:
            logger.exception("Failed to get task %s", task_id)
            return None
        except Exception:
            logger.exception("Failed to deserialize task %s", task_id)
            return None

    def save_job(self, job: ScrapeJob) -> None:
        try:
            self.redis.set(f"job:{job.id}", job.model_dump_json())
            self.redis.sadd("jobs:all", str(job.id))
        except redis.RedisError:
            logger.exception("Failed to save job %s", job.id)

    def get_job(self, job_id: str) -> Optional[ScrapeJob]:
        try:
            raw = self.redis.get(f"job:{job_id}")
            if raw is None:
                return None
            return ScrapeJob.model_validate_json(raw)
        except redis.RedisError:
            logger.exception("Failed to get job %s", job_id)
            return None
        except Exception:
            logger.exception("Failed to deserialize job %s", job_id)
            return None

    def get_all_jobs(self) -> list[ScrapeJob]:
        jobs: list[ScrapeJob] = []
        try:
            job_ids = self.redis.smembers("jobs:all") or set()
        except redis.RedisError:
            logger.exception("Failed to list jobs")
            return jobs

        for job_id in job_ids:
            job = self.get_job(str(job_id))
            if job is not None:
                jobs.append(job)

        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs

    # --- Worker registry methods ---
    def register_worker(self, worker: WorkerInfo) -> None:
        try:
            self.redis.set(f"worker:{worker.id}", worker.model_dump_json(), ex=60)
            self.redis.sadd("workers:all", worker.id)
        except redis.RedisError:
            logger.exception("Failed to register worker %s", worker.id)

    def update_worker_heartbeat(self, worker_id: str) -> None:
        try:
            raw = self.redis.get(f"worker:{worker_id}")
            if raw is None:
                return
            worker = WorkerInfo.model_validate_json(raw)
            worker.last_heartbeat = _now_utc()
            self.redis.set(f"worker:{worker_id}", worker.model_dump_json(), ex=60)
        except redis.RedisError:
            logger.exception("Failed to update worker heartbeat %s", worker_id)
        except Exception:
            logger.exception("Failed to deserialize worker %s", worker_id)

    def get_all_workers(self) -> list[WorkerInfo]:
        workers: list[WorkerInfo] = []
        try:
            worker_ids = self.redis.smembers("workers:all") or set()
        except redis.RedisError:
            logger.exception("Failed to list workers")
            return workers

        for worker_id in worker_ids:
            try:
                raw = self.redis.get(f"worker:{worker_id}")
                if raw is None:
                    continue
                workers.append(WorkerInfo.model_validate_json(raw))
            except redis.RedisError:
                logger.exception("Failed to get worker %s", worker_id)
            except Exception:
                logger.exception("Failed to deserialize worker %s", worker_id)

        return workers

    def mark_workers_offline(self, timeout_seconds: int = 30) -> None:
        now = _now_utc()
        for worker in self.get_all_workers():
            try:
                age_seconds = (now - worker.last_heartbeat).total_seconds()
                if age_seconds > timeout_seconds and worker.status != WorkerStatus.offline:
                    worker.status = WorkerStatus.offline
                    self.redis.set(
                        f"worker:{worker.id}",
                        worker.model_dump_json(),
                        ex=60,
                    )
            except redis.RedisError:
                logger.exception("Failed to mark worker offline %s", worker.id)
            except Exception:
                logger.exception("Failed while evaluating worker %s", worker.id)

