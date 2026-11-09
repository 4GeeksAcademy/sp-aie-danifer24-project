"""Celery application configuration for background jobs."""

import os

from celery import Celery


redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
result_backend_url = os.getenv("CELERY_RESULT_BACKEND", redis_url)

celery_app = Celery(
    "nexova",
    broker=redis_url,
    backend=result_backend_url,
    include=["services.tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=3600,
    task_time_limit=3660,
    task_default_retry_delay=2,
    worker_send_task_events=True,
    task_send_sent_event=True,
)
