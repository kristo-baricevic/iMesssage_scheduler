from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from .models import DeliveryThrottle, MessageStatus, MessageStatusEvent, ScheduledMessage


@dataclass(frozen=True)
class ClaimedMessage:
    id: str
    to_handle: str
    body: str
    scheduled_for: str


def _log_status(message: ScheduledMessage, status: str, detail: Optional[dict] = None) -> None:
    MessageStatusEvent.objects.create(
        message=message,
        status=status,
        detail=detail or None,
    )


@transaction.atomic
def claim_next_message(*, gateway_id: str) -> Optional[ClaimedMessage]:
    now = timezone.now()

    throttle = DeliveryThrottle.objects.select_for_update().get_or_create(id=1)[0]
    if now < throttle.next_send_at:
        return None

    msg = (
        ScheduledMessage.objects.select_for_update(skip_locked=True)
        .filter(
            status=MessageStatus.QUEUED,
            scheduled_for__lte=now,
        )
        .order_by("created_at", "id")
        .first()
    )

    if not msg:
        return None

    msg.status = MessageStatus.ACCEPTED
    msg.claimed_at = now
    msg.claimed_by = gateway_id
    msg.save(update_fields=["status", "claimed_at", "claimed_by", "updated_at"])

    _log_status(msg, MessageStatus.ACCEPTED, {"gateway_id": gateway_id})

    throttle.next_send_at = now + timedelta(seconds=throttle.interval_seconds)
    throttle.save(update_fields=["next_send_at"])

    return ClaimedMessage(
        id=str(msg.id),
        to_handle=msg.to_handle,
        body=msg.body,
        scheduled_for=msg.scheduled_for.isoformat(),
    )
