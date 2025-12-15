from __future__ import annotations

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import (
    DeliveryThrottle,
    MessageStatus,
    MessageStatusEvent,
    ScheduledMessage,
)


@shared_task(name="scheduler.tasks.scheduler_tick")
def scheduler_tick(limit: int = 50):
    now = timezone.now()

    with transaction.atomic():
        try:
            throttle = DeliveryThrottle.objects.select_for_update().get(pk=1)
        except DeliveryThrottle.DoesNotExist:
            throttle = DeliveryThrottle.objects.create(id=1)

        if now < throttle.next_send_at:
            return {
                "skipped": True,
                "reason": "throttled",
                "next_send_at": throttle.next_send_at.isoformat(),
            }

        msg = (
            ScheduledMessage.objects.select_for_update(skip_locked=True)
            .filter(
                status=MessageStatus.QUEUED,
                scheduled_for__lte=now,
                claimed_at__isnull=True,
            )
            .exclude(attempt_count__gte=throttle.max_attempts)
            .order_by("scheduled_for", "created_at")
            .first()
        )

        if not msg:
            return {"skipped": True, "reason": "no_due_messages"}

        msg.status = MessageStatus.ACCEPTED
        msg.claimed_at = now
        msg.claimed_by = "gateway_pending"
        msg.save(update_fields=["status", "claimed_at", "claimed_by", "updated_at"])

        MessageStatusEvent.objects.create(
            message=msg,
            status=MessageStatus.ACCEPTED,
            detail={"claimed_by": msg.claimed_by},
        )

        throttle.next_send_at = now + timezone.timedelta(seconds=throttle.interval_seconds)
        throttle.save(update_fields=["next_send_at"])

        return {"ready": True, "id": str(msg.id)}
