"""Background jobs.

APScheduler by default, because it needs no external service. A self-hoster
who outgrows it can swap in Celery and Redis without touching the job
functions, which are plain async functions and know nothing about how they
are scheduled.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.jobs.unread_notifier import notify_unread

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    scheduler.add_job(
        notify_unread,
        trigger="interval",
        minutes=1,
        id="unread_notifier",
        # If the process was busy or asleep, run once on resume rather than
        # firing every missed minute in a burst.
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )
    scheduler.start()
    logger.info("scheduler started")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("scheduler stopped")
