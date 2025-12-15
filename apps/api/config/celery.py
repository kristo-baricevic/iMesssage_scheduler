import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "scheduler-tick-every-5-seconds": {
        "task": "scheduler.tasks.scheduler_tick",
        "schedule": 5.0,
    }
}
