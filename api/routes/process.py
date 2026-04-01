"""Process job endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.dependencies import db
from api.jobs import JobStatus, registry
from api.models.jobs import JobOut, ProcessRequest

router = APIRouter(prefix="/api")


def _run_process(job_id: str, req: ProcessRequest) -> None:
    registry.update(job_id, JobStatus.RUNNING)
    try:
        from pipeline.runner import run_pipeline
        total = {"processed": 0, "matched": 0, "classified_positive": 0}
        while True:
            summary = run_pipeline(db, batch_size=req.batch_size, verbose=False, use_keyword_filter=req.use_keyword_filter)
            for k in total:
                total[k] += summary[k]
            if summary["processed"] == 0:
                break
        registry.update(job_id, JobStatus.DONE, summary=total)
    except Exception as exc:
        registry.update(job_id, JobStatus.FAILED, error=str(exc))


@router.post("/process", response_model=JobOut, status_code=202)
def start_process(req: ProcessRequest, background_tasks: BackgroundTasks):
    job = registry.create()
    background_tasks.add_task(_run_process, job.id, req)
    return _job_to_out(job)


@router.get("/process/{job_id}", response_model=JobOut)
def get_process_job(job_id: str):
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_out(job)


def _job_to_out(job) -> JobOut:
    return JobOut(
        job_id=job.id,
        status=job.status.value,
        summary=job.summary,
        error=job.error,
    )
