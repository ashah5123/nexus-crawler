from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from orchestrator.state import StateManager
from shared.models import ScrapeJob, ScrapeTask, WorkerInfo
from shared.queue import TaskQueue


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class CreateJobRequest(BaseModel):
    name: str
    urls: list[str] = Field(default_factory=list)

    @field_validator("urls")
    @classmethod
    def _validate_urls(cls, urls: list[str]) -> list[str]:
        if not (1 <= len(urls) <= 1000):
            raise ValueError("urls must contain between 1 and 1000 items")
        for u in urls:
            if not isinstance(u, str) or not u.startswith("http"):
                raise ValueError("each url must start with http")
        return urls


async def get_queue() -> TaskQueue:
    return app.state.queue


async def get_state_manager() -> StateManager:
    return app.state.state_manager


QueueDep = Annotated[TaskQueue, Depends(get_queue)]
StateDep = Annotated[StateManager, Depends(get_state_manager)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    app.state.queue = TaskQueue(redis_url=redis_url)
    app.state.state_manager = StateManager(queue=app.state.queue)
    yield


app = FastAPI(title="Nexus Crawler API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": _now_utc()}


@app.post("/jobs", response_model=ScrapeJob)
async def create_job(body: CreateJobRequest, sm: StateDep):
    return sm.create_job(name=body.name, urls=body.urls)


@app.get("/jobs", response_model=list[ScrapeJob])
async def list_jobs(sm: StateDep):
    return sm.get_all_jobs()


@app.get("/jobs/{job_id}", response_model=ScrapeJob)
async def get_job(job_id: str, sm: StateDep):
    job = sm.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/jobs/{job_id}/tasks", response_model=list[ScrapeTask])
async def get_job_tasks(job_id: str, queue: QueueDep):
    tasks: list[ScrapeTask] = []
    try:
        keys = queue.redis.keys("task:*")
    except Exception:
        # TaskQueue already logs its own calls; this is a direct redis call.
        raise HTTPException(status_code=500, detail="Failed to list tasks")

    for key in keys:
        task_id = key.removeprefix("task:")
        task = queue.get_task(task_id)
        if task is not None and task.job_id == job_id:
            tasks.append(task)
    return tasks


@app.get("/workers", response_model=list[WorkerInfo])
async def get_workers(queue: QueueDep):
    queue.mark_workers_offline()
    return queue.get_all_workers()


@app.get("/stats")
async def get_stats(queue: QueueDep, sm: StateDep):
    jobs = sm.get_all_jobs()
    queue.mark_workers_offline()
    workers = queue.get_all_workers()
    queue_length = queue.get_queue_length()

    running_jobs = sum(1 for j in jobs if j.status == "running")
    active_workers = sum(1 for w in workers if w.status != "offline")

    return {
        "total_jobs": len(jobs),
        "running_jobs": running_jobs,
        "active_workers": active_workers,
        "queue_length": queue_length,
    }


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str, queue: QueueDep):
    job = queue.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = "failed"
    job.updated_at = _now_utc()
    queue.save_job(job)
    return {"ok": True}

