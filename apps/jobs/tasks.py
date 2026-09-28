"""Huey consumer: `uv run python manage.py run_huey`."""
from huey import crontab
from huey.contrib.djhuey import periodic_task
from .services import run_daily_handoff, send_due_messages


@periodic_task(crontab(minute="*"))
def dispatch_due_messages():
    send_due_messages()


@periodic_task(crontab(minute="*"))
def roll_local_kitchen_days():
    run_daily_handoff()
