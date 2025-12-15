from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from django.conf import settings

from .models import DeliveryThrottle, MessageStatus, MessageStatusEvent, ScheduledMessage

logger = logging.getLogger(__name__)

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

    # 1) First: claim messages already prepared by Celery (ACCEPTED + gateway_pending)
    msg = (
        ScheduledMessage.objects.select_for_update(skip_locked=True)
        .filter(
            status=MessageStatus.ACCEPTED,
            claimed_by="gateway_pending",
            claimed_at__isnull=True,
            scheduled_for__lte=now,
        )
        .order_by("scheduled_for", "created_at", "id")
        .first()
    )

    if msg:
        msg.claimed_at = now
        msg.claimed_by = gateway_id
        msg.save(update_fields=["claimed_at", "claimed_by", "updated_at"])

        _log_status(msg, MessageStatus.ACCEPTED, {"gateway_id": gateway_id, "source": "gateway_claim"})

        logger.info("claim success", extra={"gateway_id": gateway_id, "message_id": str(msg.id)})

        return ClaimedMessage(
            id=str(msg.id),
            to_handle=msg.to_handle,
            body=msg.body,
            scheduled_for=msg.scheduled_for.isoformat(),
        )

    # 2) Fallback: old path (directly claiming QUEUED)
    throttle = DeliveryThrottle.objects.select_for_update().get_or_create(id=1)[0]
    if now < throttle.next_send_at:
        logger.info(
            "claim blocked by throttle",
            extra={"gateway_id": gateway_id, "next_send_at": throttle.next_send_at.isoformat()},
        )
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
        logger.info("claim found no message", extra={"gateway_id": gateway_id})
        return None

    msg.status = MessageStatus.ACCEPTED
    msg.claimed_at = now
    msg.claimed_by = gateway_id
    msg.save(update_fields=["status", "claimed_at", "claimed_by", "updated_at"])

    _log_status(msg, MessageStatus.ACCEPTED, {"gateway_id": gateway_id})

    throttle.next_send_at = now + timedelta(seconds=throttle.interval_seconds)
    throttle.save(update_fields=["next_send_at"])

    logger.info("claim success", extra={"gateway_id": gateway_id, "message_id": str(msg.id)})

    return ClaimedMessage(
        id=str(msg.id),
        to_handle=msg.to_handle,
        body=msg.body,
        scheduled_for=msg.scheduled_for.isoformat(),
    )
