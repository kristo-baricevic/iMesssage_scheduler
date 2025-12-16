from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.test import TransactionTestCase

from scheduler.models import DeliveryThrottle, MessageStatus, ScheduledMessage
from scheduler.services import claim_next_message
from scheduler.tasks import scheduler_tick


class ThrottleIntervalTests(TransactionTestCase):
    FIXED_NOW = datetime(2025, 12, 16, 5, 11, 54, tzinfo=dt_timezone.utc)

    def _make_throttle(
        self,
        *,
        interval_seconds: int = 3600,
        next_send_at: datetime | None = None,
        max_attempts: int = 3,
        retry_base_seconds: int = 5,
        retry_max_seconds: int = 60,
    ) -> DeliveryThrottle:
        if next_send_at is None:
            next_send_at = self.FIXED_NOW - timedelta(seconds=1)

        DeliveryThrottle.objects.all().delete()
        return DeliveryThrottle.objects.create(
            id=1,
            interval_seconds=interval_seconds,
            next_send_at=next_send_at,
            max_attempts=max_attempts,
            retry_base_seconds=retry_base_seconds,
            retry_max_seconds=retry_max_seconds,
        )

    def _make_due_message(self, *, now: datetime | None = None) -> ScheduledMessage:
        if now is None:
            now = self.FIXED_NOW
        return ScheduledMessage.objects.create(
            to_handle="+15551234567",
            body="hi",
            scheduled_for=now - timedelta(seconds=1),
            status=MessageStatus.QUEUED,
            claimed_at=None,
            claimed_by=None,
            attempt_count=0,
        )

    @patch("scheduler.tasks.timezone.now")
    def test_scheduler_tick_advances_next_send_at_by_interval_seconds(self, now_mock):
        fixed_now = self.FIXED_NOW
        now_mock.return_value = fixed_now

        throttle = self._make_throttle(
            interval_seconds=60,
            next_send_at=fixed_now - timedelta(seconds=1),
        )
        self._make_due_message(now=fixed_now)

        scheduler_tick(limit=50)

        throttle.refresh_from_db()
        self.assertEqual(throttle.next_send_at, fixed_now + timedelta(seconds=60))

    @patch("scheduler.services.timezone.now")
    def test_claim_next_message_blocks_when_next_send_at_in_future(self, now_mock):
        fixed_now = self.FIXED_NOW
        now_mock.return_value = fixed_now

        self._make_throttle(
            interval_seconds=10,
            next_send_at=fixed_now + timedelta(seconds=999),
        )
        self._make_due_message(now=fixed_now)

        claimed = claim_next_message(gateway_id="mac-1")
        self.assertIsNone(claimed)

    @patch("scheduler.services.timezone.now")
    def test_claim_next_message_advances_next_send_at_by_interval_seconds_when_it_claims(self, now_mock):
        fixed_now = self.FIXED_NOW
        now_mock.return_value = fixed_now

        throttle = self._make_throttle(
            interval_seconds=15,
            next_send_at=fixed_now - timedelta(seconds=1),
        )
        msg = self._make_due_message(now=fixed_now)

        claimed = claim_next_message(gateway_id="mac-1")
        self.assertIsNotNone(claimed)

        throttle.refresh_from_db()
        msg.refresh_from_db()

        self.assertEqual(throttle.next_send_at, fixed_now + timedelta(seconds=15))
        self.assertEqual(msg.status, MessageStatus.ACCEPTED)
        self.assertEqual(msg.claimed_by, "mac-1")
        self.assertEqual(msg.claimed_at, fixed_now)

    @patch("scheduler.tasks.timezone.now")
    def test_scheduler_tick_respects_db_interval_seconds(self, now_mock):
        fixed_now = self.FIXED_NOW
        now_mock.return_value = fixed_now

        throttle = self._make_throttle(
            interval_seconds=7,
            next_send_at=fixed_now - timedelta(seconds=1),
        )
        self._make_due_message(now=fixed_now)

        scheduler_tick(limit=50)

        throttle.refresh_from_db()
        self.assertEqual(throttle.next_send_at, fixed_now + timedelta(seconds=7))
