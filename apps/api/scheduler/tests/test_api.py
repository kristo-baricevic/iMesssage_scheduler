import uuid

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from datetime import timedelta

from scheduler.models import DeliveryThrottle, MessageStatus, MessageStatusEvent, ScheduledMessage


class MessageApiTests(APITestCase):
    def setUp(self) -> None:
        DeliveryThrottle.objects.update_or_create(
            id=1,
            defaults={"interval_seconds": 3600, "next_send_at": timezone.now() - timedelta(seconds=1)},
        )

    def test_create_message_sets_queued_and_logs_event(self):
        payload = {
            "to_handle": "+15551230001",
            "body": "hello",
            "scheduled_for": (timezone.now() + timedelta(minutes=5)).isoformat(),
        }

        res = self.client.post("/api/messages/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        msg_id = res.data["id"]
        msg = ScheduledMessage.objects.get(id=msg_id)

        self.assertEqual(msg.to_handle, payload["to_handle"])
        self.assertEqual(msg.body, payload["body"])
        self.assertEqual(msg.status, MessageStatus.QUEUED)

        self.assertTrue(
            MessageStatusEvent.objects.filter(message=msg, status=MessageStatus.QUEUED).exists()
        )

    def test_list_messages_can_filter_by_status(self):
        now = timezone.now()
        m1 = ScheduledMessage.objects.create(
            to_handle="+15551230001",
            body="one",
            scheduled_for=now,
            status=MessageStatus.QUEUED,
        )
        m2 = ScheduledMessage.objects.create(
            to_handle="+15551230002",
            body="two",
            scheduled_for=now,
            status=MessageStatus.SENT,
        )

        res = self.client.get("/api/messages/?status=QUEUED")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        ids = [row["id"] for row in res.data]
        self.assertIn(str(m1.id), ids)
        self.assertNotIn(str(m2.id), ids)


class GatewayApiTests(APITestCase):
    def setUp(self) -> None:
        DeliveryThrottle.objects.update_or_create(
            id=1,
            defaults={"interval_seconds": 3600, "next_send_at": timezone.now() - timedelta(seconds=1)},
        )

    def test_claim_requires_gateway_id(self):
        res = self.client.post("/api/gateway/claim/", {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_claim_returns_204_when_no_messages(self):
        res = self.client.post("/api/gateway/claim/", {"gateway_id": "mac-1"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

    def test_claim_skips_future_messages(self):
        ScheduledMessage.objects.create(
            to_handle="+15551230001",
            body="future",
            scheduled_for=timezone.now() + timedelta(minutes=10),
            status=MessageStatus.QUEUED,
        )

        res = self.client.post("/api/gateway/claim/", {"gateway_id": "mac-1"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

    def test_claim_returns_oldest_fifo_and_marks_accepted(self):
        now = timezone.now()

        m1 = ScheduledMessage.objects.create(
            to_handle="+15551230001",
            body="first",
            scheduled_for=now - timedelta(minutes=1),
            status=MessageStatus.QUEUED,
        )
        m2 = ScheduledMessage.objects.create(
            to_handle="+15551230002",
            body="second",
            scheduled_for=now - timedelta(minutes=1),
            status=MessageStatus.QUEUED,
        )

        res = self.client.post("/api/gateway/claim/", {"gateway_id": "mac-1"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["id"], str(m1.id))

        m1.refresh_from_db()
        self.assertEqual(m1.status, MessageStatus.ACCEPTED)
        self.assertEqual(m1.claimed_by, "mac-1")
        self.assertIsNotNone(m1.claimed_at)

        self.assertTrue(
            MessageStatusEvent.objects.filter(message=m1, status=MessageStatus.ACCEPTED).exists()
        )

        # Throttle blocks immediate second claim
        res2 = self.client.post("/api/gateway/claim/", {"gateway_id": "mac-1"}, format="json")
        self.assertEqual(res2.status_code, status.HTTP_204_NO_CONTENT)

        # Move throttle back and claim next
        DeliveryThrottle.objects.filter(id=1).update(next_send_at=timezone.now() - timedelta(seconds=1))
        res3 = self.client.post("/api/gateway/claim/", {"gateway_id": "mac-1"}, format="json")
        self.assertEqual(res3.status_code, status.HTTP_200_OK)
        self.assertEqual(res3.data["id"], str(m2.id))

    def test_report_requires_message_id_and_status(self):
        res = self.client.post("/api/gateway/report/", {"status": "SENT"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        res = self.client.post("/api/gateway/report/", {"message_id": str(uuid.uuid4())}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_report_rejects_invalid_status(self):
        msg = ScheduledMessage.objects.create(
            to_handle="+15551230001",
            body="hi",
            scheduled_for=timezone.now() - timedelta(minutes=1),
            status=MessageStatus.ACCEPTED,
        )

        res = self.client.post(
            "/api/gateway/report/",
            {"message_id": str(msg.id), "status": "QUEUED"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_report_404_when_message_missing(self):
        res = self.client.post(
            "/api/gateway/report/",
            {"message_id": str(uuid.uuid4()), "status": MessageStatus.SENT},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_report_sent_updates_status_and_logs_event(self):
        msg = ScheduledMessage.objects.create(
            to_handle="+15551230001",
            body="hi",
            scheduled_for=timezone.now() - timedelta(minutes=1),
            status=MessageStatus.ACCEPTED,
        )

        res = self.client.post(
            "/api/gateway/report/",
            {"message_id": str(msg.id), "status": MessageStatus.SENT},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        msg.refresh_from_db()
        self.assertEqual(msg.status, MessageStatus.SENT)

        self.assertTrue(
            MessageStatusEvent.objects.filter(message=msg, status=MessageStatus.SENT).exists()
        )

    def test_report_failed_increments_attempt_and_sets_last_error(self):
        msg = ScheduledMessage.objects.create(
            to_handle="+15551230001",
            body="hi",
            scheduled_for=timezone.now() - timedelta(minutes=1),
            status=MessageStatus.ACCEPTED,
        )

        res = self.client.post(
            "/api/gateway/report/",
            {
                "message_id": str(msg.id),
                "status": MessageStatus.FAILED,
                "error": "osascript failed",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        msg.refresh_from_db()
        self.assertEqual(msg.status, MessageStatus.FAILED)
        self.assertEqual(msg.attempt_count, 1)
        self.assertEqual(msg.last_error, "osascript failed")

        self.assertTrue(
            MessageStatusEvent.objects.filter(message=msg, status=MessageStatus.FAILED).exists()
        )
