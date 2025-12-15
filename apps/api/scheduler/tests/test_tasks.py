from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from scheduler.models import (
    DeliveryThrottle,
    MessageStatus,
    MessageStatusEvent,
    ScheduledMessage,
)
from scheduler.tasks import scheduler_tick


class SchedulerTickTests(TestCase):
    def setUp(self):
        self.now = timezone.now().replace(microsecond=0)
        self.throttle = DeliveryThrottle.get_solo()
        self.throttle.interval_seconds = 60
        self.throttle.max_attempts = 5
        self.throttle.retry_base_seconds = 60
        self.throttle.retry_max_seconds = 3600
        self.throttle.next_send_at = self.now
        self.throttle.save()

    def test_skips_when_throttled(self):
        self.throttle.next_send_at = self.now + timedelta(seconds=30)
        self.throttle.save(update_fields=["next_send_at"])

        with patch("scheduler.tasks.timezone.now", return_value=self.now):
            res = scheduler_tick()

        self.assertTrue(res["skipped"])
        self.assertEqual(res["reason"], "throttled")

    def test_skips_when_no_due_messages(self):
        ScheduledMessage.objects.create(
            to_handle="+15551230001",
            body="hi",
            scheduled_for=self.now + timedelta(minutes=5),
            status=MessageStatus.QUEUED,
        )

        with patch("scheduler.tasks.timezone.now", return_value=self.now):
            res = scheduler_tick()

        self.assertTrue(res["skipped"])
        self.assertEqual(res["reason"], "no_due_messages")

    def test_claims_single_due_message_and_creates_event_and_updates_throttle(self):
        msg = ScheduledMessage.objects.create(
            to_handle="+15551230001",
            body="hi",
            scheduled_for=self.now - timedelta(minutes=1),
            status=MessageStatus.QUEUED,
        )

        with patch("scheduler.tasks.timezone.now", return_value=self.now):
            res = scheduler_tick()

        msg.refresh_from_db()
        self.throttle.refresh_from_db()

        self.assertTrue(res["ready"])
        self.assertEqual(res["id"], str(msg.id))

        self.assertEqual(msg.status, MessageStatus.ACCEPTED)
        self.assertEqual(msg.claimed_by, "gateway_pending")
        self.assertEqual(msg.claimed_at, self.now)

        ev = MessageStatusEvent.objects.filter(message=msg, status=MessageStatus.ACCEPTED).first()
        self.assertIsNotNone(ev)
        self.assertEqual(ev.detail["claimed_by"], "gateway_pending")

        self.assertEqual(self.throttle.next_send_at, self.now + timedelta(seconds=self.throttle.interval_seconds))

    def test_fifo_by_scheduled_for_then_created_at(self):
        m1 = ScheduledMessage.objects.create(
            to_handle="+15550000001",
            body="first",
            scheduled_for=self.now - timedelta(minutes=2),
            status=MessageStatus.QUEUED,
        )
        m2 = ScheduledMessage.objects.create(
            to_handle="+15550000002",
            body="second",
            scheduled_for=self.now - timedelta(minutes=1),
            status=MessageStatus.QUEUED,
        )

        with patch("scheduler.tasks.timezone.now", return_value=self.now):
            res = scheduler_tick()

        m1.refresh_from_db()
        m2.refresh_from_db()

        self.assertEqual(res["id"], str(m1.id))
        self.assertEqual(m1.status, MessageStatus.ACCEPTED)
        self.assertEqual(m2.status, MessageStatus.QUEUED)

    def test_skips_messages_at_or_over_max_attempts(self):
        msg = ScheduledMessage.objects.create(
            to_handle="+15551230001",
            body="hi",
            scheduled_for=self.now - timedelta(minutes=1),
            status=MessageStatus.QUEUED,
            attempt_count=self.throttle.max_attempts,
        )

        with patch("scheduler.tasks.timezone.now", return_value=self.now):
            res = scheduler_tick()

        msg.refresh_from_db()
        self.assertTrue(res["skipped"])
        self.assertEqual(res["reason"], "no_due_messages")
        self.assertEqual(msg.status, MessageStatus.QUEUED)

    def test_skips_already_claimed_messages(self):
        msg = ScheduledMessage.objects.create(
            to_handle="+15551230001",
            body="hi",
            scheduled_for=self.now - timedelta(minutes=1),
            status=MessageStatus.QUEUED,
            claimed_at=self.now - timedelta(seconds=10),
            claimed_by="mac-1",
        )

        with patch("scheduler.tasks.timezone.now", return_value=self.now):
            res = scheduler_tick()

        msg.refresh_from_db()
        self.assertTrue(res["skipped"])
        self.assertEqual(res["reason"], "no_due_messages")
        self.assertEqual(msg.status, MessageStatus.QUEUED)
