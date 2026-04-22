"""Background scheduler: scrape → classify → notify."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from api.dependencies import db
from notifier.sender import ConsultationAlert, send_digest
from pipeline.runner import run_pipeline
from scraper.config import ScrapeConfig
from scraper.crawler import crawl_paginated

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _load_configs() -> list[ScrapeConfig]:
    raw = os.environ.get("SCHEDULER_CONFIGS", "")
    configs = []
    for path in filter(None, (p.strip() for p in raw.split(","))):
        try:
            import json5
            with open(path) as f:
                configs.append(ScrapeConfig.from_dict(json5.load(f)))
        except Exception:
            logger.exception("Failed to load scheduler config: %s", path)
    return configs


def run_monitor_cycle() -> None:
    """One full scrape → classify → notify cycle."""
    settings = db.get_scheduler_settings()

    for cfg in _load_configs():
        session_id = db.create_crawl_session(
            triggered_at=datetime.now(timezone.utc).isoformat(),
            trigger_source="scheduler",
            config_url=cfg.url,
        )
        try:
            summary = crawl_paginated(
                cfg.url, db,
                selector=cfg.selector,
                max_pages=cfg.max_pages,
                max_workers=cfg.workers,
                page_separator=cfg.page_separator,
                page_prefix=cfg.page_prefix,
                page_suffix=cfg.page_suffix,
                verbose=False,
            )
            db.finish_crawl_session(session_id, summary)
            db.link_articles_to_session(session_id, summary["article_ids"])
            logger.info("Scraped %s: %s", cfg.url, summary)
        except Exception:
            db.fail_crawl_session(session_id, "scrape failed")
            logger.exception("Scrape failed for %s", cfg.url)

    try:
        pipeline_summary = run_pipeline(
            db,
            verbose=False,
            use_keyword_filter=settings.use_keyword_filter,
            batch_size=settings.batch_size,
            reprocess_all=settings.reprocess_all,
        )
        logger.info("Pipeline: %s", pipeline_summary)
    except Exception:
        logger.exception("Pipeline failed")
        return

    unnotified = db.list_unnotified_consultations()
    if not unnotified:
        logger.info("No new consultations to notify")
        return

    alerts = []
    for article in unnotified:
        analysis = db.get_analysis(article.id)
        if analysis is None:
            continue
        alerts.append(ConsultationAlert(
            article_id=article.id,
            title=article.title,
            url=article.url,
            date=article.date,
            classifier_score=analysis.classifier_score,
            extracted_date=analysis.extracted_date,
            extracted_time=analysis.extracted_time,
            extracted_place=analysis.extracted_place,
            extracted_subject=analysis.extracted_subject,
        ))

    if not alerts:
        return

    try:
        send_digest(alerts)
        notified_at = datetime.now(timezone.utc).isoformat()
        for article in unnotified:
            db.set_notified(article.id, notified_at)
        logger.info("Sent notification for %d consultation(s)", len(alerts))
    except Exception:
        logger.exception("Notification failed — articles NOT marked notified, will retry next cycle")


def apply_settings() -> None:
    """Re-read settings from DB and reschedule / pause / resume the job."""
    global _scheduler
    if _scheduler is None:
        return
    settings = db.get_scheduler_settings()
    job = _scheduler.get_job("monitor_cycle")
    if settings.enabled:
        if job is None:
            _scheduler.add_job(
                run_monitor_cycle,
                trigger="interval",
                minutes=settings.interval_minutes,
                id="monitor_cycle",
                max_instances=1,
                coalesce=True,
            )
        else:
            _scheduler.reschedule_job(
                "monitor_cycle",
                trigger="interval",
                minutes=settings.interval_minutes,
            )
            job.resume()
        logger.info("Scheduler applied: enabled, interval=%d min", settings.interval_minutes)
    else:
        if job is not None:
            job.pause()
        logger.info("Scheduler applied: disabled")


def create_scheduler() -> BackgroundScheduler | None:
    """Create the APScheduler instance, or None if SCHEDULER_ENABLED=false."""
    global _scheduler
    # Env-var gate: hard-disable (useful in tests / dev without touching DB)
    if os.environ.get("SCHEDULER_ENABLED", "true").lower() not in ("1", "true", "yes"):
        logger.info("Scheduler disabled via SCHEDULER_ENABLED")
        return None

    settings = db.get_scheduler_settings()

    scheduler = BackgroundScheduler()
    if settings.enabled:
        scheduler.add_job(
            run_monitor_cycle,
            trigger="interval",
            minutes=settings.interval_minutes,
            id="monitor_cycle",
            max_instances=1,
            coalesce=True,
        )
    _scheduler = scheduler
    logger.info("Scheduler configured: enabled=%s interval=%d min",
                settings.enabled, settings.interval_minutes)
    return scheduler
