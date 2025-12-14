from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from scheduler.models import DeliveryThrottle, MessageStatus, ScheduledMessage
from scheduler.services import claim_next_message


class ClaimNextMessageTests(TestCase):
    def setUp(self) -> None:
        DeliveryThrottle.objects.update_or_create(
            id=1,
            defaults={"interval_seconds": 3600, "next_send_at": timezone.now() - timedelta(seconds=1)},
        )

    def test_returns_none_when_no_messages(self):
        claimed = claim_next_message(gateway_id="mac-1")
        self.assertIsNone(claimed)

    def test_skips_messages_scheduled_in_future(self):
        ScheduledMessage.objects.create(
            to_handle="+15551230001",
            body="future",
            scheduled_for=timezone.now() + timedelta(minutes=10),
        )

        claimed = claim_next_message(gateway_id="mac-1")
        self.assertIsNone(claimed)

    def test_claims_oldest_message_fifo(self):
        now = timezone.now()

        m1 = ScheduledMessage.objects.create(
            to_handle="+15551230001",
            body="first",
            scheduled_for=now - timedelta(minutes=1),
        )
        m2 = ScheduledMessage.objects.create(
            to_handle="+15551230002",
            body="second",
            scheduled_for=now - timedelta(minutes=1),
        )

        claimed1 = claim_next_message(gateway_id="mac-1")
        self.assertIsNotNone(claimed1)
        self.assertEqual(claimed1.id, str(m1.id))

        m1.refresh_from_db()
        self.assertEqual(m1.status, MessageStatus.ACCEPTED)
        self.assertEqual(m1.claimed_by, "mac-1")
        self.assertIsNotNone(m1.claimed_at)

        # Throttle should now block immediate second claim
        claimed2 = claim_next_message(gateway_id="mac-1")
        self.assertIsNone(claimed2)

        # Move throttle back and claim next
        DeliveryThrottle.objects.filter(id=1).update(next_send_at=timezone.now() - timedelta(seconds=1))
        claimed3 = claim_next_message(gateway_id="mac-1")
        self.assertIsNotNone(claimed3)
        self.assertEqual(claimed3.id, str(m2.id))

    def test_throttle_blocks_claims_until_next_send_at(self):
        ScheduledMessage.objects.create(
            to_handle="+15551230001",
            body="hi",
            scheduled_for=timezone.now() - timedelta(minutes=1),
        )

        DeliveryThrottle.objects.filter(id=1).update(next_send_at=timezone.now() + timedelta(hours=1))

        claimed = claim_next_message(gateway_id="mac-1")
        self.assertIsNone(claimed)
