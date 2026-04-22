"""Scheduler settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.dependencies import db
from api.scheduler import apply_settings
from scraper.database import SchedulerSettings

router = APIRouter(prefix="/api")


class SchedulerSettingsOut(BaseModel):
    enabled: bool
    interval_minutes: int
    use_keyword_filter: bool
    batch_size: int
    reprocess_all: bool


class SchedulerSettingsIn(BaseModel):
    enabled: bool
    interval_minutes: int = Field(ge=1)
    use_keyword_filter: bool
    batch_size: int = Field(ge=1, le=500)
    reprocess_all: bool


@router.get("/scheduler/settings", response_model=SchedulerSettingsOut)
def get_scheduler_settings():
    s = db.get_scheduler_settings()
    return SchedulerSettingsOut(
        enabled=s.enabled,
        interval_minutes=s.interval_minutes,
        use_keyword_filter=s.use_keyword_filter,
        batch_size=s.batch_size,
        reprocess_all=s.reprocess_all,
    )


@router.put("/scheduler/settings", response_model=SchedulerSettingsOut)
def update_scheduler_settings(body: SchedulerSettingsIn):
    s = SchedulerSettings(
        enabled=body.enabled,
        interval_minutes=body.interval_minutes,
        use_keyword_filter=body.use_keyword_filter,
        batch_size=body.batch_size,
        reprocess_all=body.reprocess_all,
    )
    db.save_scheduler_settings(s)
    apply_settings()
    return SchedulerSettingsOut(**body.model_dump())
