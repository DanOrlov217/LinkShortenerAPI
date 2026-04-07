from celery import Celery
from celery.schedules import crontab

from config import REDIS_URL


celery = Celery(
    "url_shortener",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks"],
)

celery.conf.beat_schedule = {
    "cleanup-expired-links": {
        "task": "tasks.cleanup_expired_links",
        "schedule": crontab(minute=0), # каждый час
    },
    "sync-popular-links-cache": {
        "task": "tasks.sync_popular_links_cache",
        "schedule": crontab(minute="*/10"), # каждые 10 минут
    },
}

celery.conf.timezone = "UTC"
