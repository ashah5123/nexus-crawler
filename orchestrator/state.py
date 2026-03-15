from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from shared.models import ScrapeJob, ScrapeResult, ScrapeTask
from shared.queue import TaskQueue


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class StateManager:
    def __init__(self, queue: TaskQueue):
        self.queue = queue
        self.logger = logging.getLogger(self.__class__.__name__)

    # --- Job lifecycle ---
    def create_job(self, name: str, urls: list[str]) -> ScrapeJob:
        job = ScrapeJob(
            name=name,
            urls=urls,
            status="pending",
            total_urls=len(urls),
        )

        self.queue.save_job(job)

        for url in urls:
            task = ScrapeTask(job_id=str(job.id), url=url)
            self.queue.save_task(task)
            self.queue.push_task(task)

        job.status = "running"
        job.updated_at = _now_utc()
        self.queue.save_job(job)
        return job

    def get_job(self, job_id: str) -> Optional[ScrapeJob]:
        return self.queue.get_job(job_id)

    def get_all_jobs(self) -> list[ScrapeJob]:
        return self.queue.get_all_jobs()

    # --- Progress updates ---
    def on_task_complete(self, job_id: str, success: bool) -> None:
        job = self.queue.get_job(job_id)
        if job is None:
            self.logger.error("Job not found for task completion: %s", job_id)
            return

        if success:
            job.completed_urls += 1
        else:
            job.failed_urls += 1

        if (job.completed_urls + job.failed_urls) >= job.total_urls:
            job.status = "completed"

        job.updated_at = _now_utc()
        self.queue.save_job(job)

    # --- Task lifecycle ---
    def start_task(self, task: ScrapeTask) -> None:
        task.status = "running"
        task.updated_at = _now_utc()
        self.queue.save_task(task)

    def complete_task(self, task: ScrapeTask, result: ScrapeResult) -> None:
        task.status = "completed"
        task.result = result
        task.updated_at = _now_utc()
        self.queue.save_task(task)
        self.on_task_complete(task.job_id, success=True)

    def fail_task(self, task: ScrapeTask, error: str) -> None:
        task.retries += 1
        task.updated_at = _now_utc()

        if task.retries < task.max_retries:
            task.status = "retrying"
            self.queue.save_task(task)
            self.queue.push_task(task)
            return

        task.status = "failed"
        task.error = error
        self.queue.save_task(task)
        self.on_task_complete(task.job_id, success=False)

