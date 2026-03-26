"""In-memory scrape job registry."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    status: JobStatus = JobStatus.PENDING
    summary: dict = field(default_factory=dict)
    error: str | None = None


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()

    def create(self) -> Job:
        job = Job(id=str(uuid.uuid4()))
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def update(self, job_id: str, status: JobStatus, summary: dict | None = None, error: str | None = None) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = status
                if summary is not None:
                    job.summary = summary
                if error is not None:
                    job.error = error


# Module-level singleton shared across the app
registry = JobRegistry()
