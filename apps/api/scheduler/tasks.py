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
from .send import send_imessage


@shared_task(name="scheduler.tasks.scheduler_tick")
def scheduler_tick(limit: int = 50):
    now = timezone.now()

    with transaction.atomic():
        throttle = DeliveryThrottle.objects.select_for_update().get(pk=1)

        if now < throttle.next_send_at:
            return {"skipped": True, "reason": "throttled", "next_send_at": throttle.next_send_at.isoformat()}

        msg = (
            ScheduledMessage.objects.select_for_update(skip_locked=True)
            .filter(
                status=MessageStatus.QUEUED,
                scheduled_for__lte=now,
            )
            .exclude(attempt_count__gte=throttle.max_attempts)
            .order_by("scheduled_for", "created_at")
            .first()
        )

        if not msg:
            return {"skipped": True, "reason": "no_due_messages"}

        msg.status = MessageStatus.ACCEPTED
        msg.claimed_at = now
        msg.claimed_by = "celery"
        msg.save(update_fields=["status", "claimed_at", "claimed_by", "updated_at"])

        MessageStatusEvent.objects.create(
            message=msg,
            status=MessageStatus.ACCEPTED,
            detail={"claimed_by": msg.claimed_by},
        )

        throttle.next_send_at = now + timezone.timedelta(seconds=throttle.interval_seconds)
        throttle.save(update_fields=["next_send_at"])

        message_id = str(msg.id)

    send_scheduled_message.delay(message_id)
    return {"enqueued": True, "id": message_id}


@shared_task(bind=True)
def send_scheduled_message(self, message_id: str):
    now = timezone.now()

    with transaction.atomic():
        throttle = DeliveryThrottle.objects.select_for_update().get(pk=1)
        msg = ScheduledMessage.objects.select_for_update().get(pk=message_id)

        if msg.status == MessageStatus.CANCELED:
            MessageStatusEvent.objects.create(
                message=msg,
                status=MessageStatus.CANCELED,
                detail={"note": "skipped_send_task_because_canceled"},
            )
            return {"skipped": True, "reason": "canceled"}

        msg.attempt_count = msg.attempt_count + 1
        msg.last_error = None
        msg.save(update_fields=["attempt_count", "last_error", "updated_at"])

    try:
        send_imessage(to_handle=msg.to_handle, body=msg.body)

        with transaction.atomic():
            msg = ScheduledMessage.objects.select_for_update().get(pk=message_id)
            if msg.status != MessageStatus.CANCELED:
                msg.status = MessageStatus.SENT
                msg.save(update_fields=["status", "updated_at"])

                MessageStatusEvent.objects.create(
                    message=msg,
                    status=MessageStatus.SENT,
                    detail={"note": "send_imessage_completed"},
                )

                msg.status = MessageStatus.DELIVERED
                msg.save(update_fields=["status", "updated_at"])

                MessageStatusEvent.objects.create(
                    message=msg,
                    status=MessageStatus.DELIVERED,
                    detail={"note": "marked_delivered_immediately"},
                )

        return {"ok": True}

    except Exception as e:
        err = str(e)

        with transaction.atomic():
            throttle = DeliveryThrottle.objects.select_for_update().get(pk=1)
            msg = ScheduledMessage.objects.select_for_update().get(pk=message_id)

            MessageStatusEvent.objects.create(
                message=msg,
                status=MessageStatus.FAILED,
                detail={"error": err, "attempt": msg.attempt_count},
            )

            msg.last_error = err

            if msg.attempt_count >= throttle.max_attempts:
                msg.status = MessageStatus.FAILED
                msg.save(update_fields=["status", "last_error", "updated_at"])
                return {"ok": False, "final_failed": True}

            attempt_index = max(msg.attempt_count - 1, 0)
            delay = min(
                throttle.retry_base_seconds * (2 ** attempt_index),
                throttle.retry_max_seconds,
            )

            msg.status = MessageStatus.QUEUED
            msg.scheduled_for = timezone.now() + timezone.timedelta(seconds=delay)
            msg.save(update_fields=["status", "scheduled_for", "last_error", "updated_at"])

            MessageStatusEvent.objects.create(
                message=msg,
                status=MessageStatus.QUEUED,
                detail={"retry_in_seconds": delay},
            )

        return {"ok": False, "requeued": True}
