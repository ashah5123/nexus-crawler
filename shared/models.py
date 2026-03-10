from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    retrying = "retrying"


class WorkerStatus(str, Enum):
    idle = "idle"
    busy = "busy"
    offline = "offline"


class ScrapeResult(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    url: str
    title: Optional[str] = None
    text_content: Optional[str] = None
    links: list[str] = Field(default_factory=list)
    status_code: int
    scraped_at: datetime = Field(default_factory=_now_utc)
    response_time_ms: float


class ScrapeJob(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID = Field(default_factory=uuid4)
    name: str
    urls: list[str]
    status: JobStatus = JobStatus.pending
    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)
    total_urls: int = 0
    completed_urls: int = 0
    failed_urls: int = 0


class ScrapeTask(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID = Field(default_factory=uuid4)
    job_id: str
    url: str
    status: TaskStatus = TaskStatus.pending
    retries: int = 0
    max_retries: int = 3
    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)
    result: Optional[ScrapeResult] = None
    error: Optional[str] = None
    domain: str = ""

    @model_validator(mode="after")
    def _set_domain_from_url(self) -> "ScrapeTask":
        if not self.domain:
            parsed = urlparse(self.url)
            self.domain = parsed.netloc or ""
        return self


class WorkerInfo(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    hostname: str
    status: WorkerStatus = WorkerStatus.idle
    current_task_id: Optional[str] = None
    last_heartbeat: datetime = Field(default_factory=_now_utc)
    tasks_completed: int = 0
    tasks_failed: int = 0

