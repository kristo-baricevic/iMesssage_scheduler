from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch
import gateway_agent as gateway

class GatewayUnitTests(unittest.TestCase):
    def test_send_imessage_success(self):
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = ""
        proc.stderr = ""

        with patch.object(gateway.subprocess, "run", return_value=proc) as run_mock:
            gateway.send_imessage(to_handle="+15551234567", body="hi")

        run_mock.assert_called_once()
        args, kwargs = run_mock.call_args
        self.assertEqual(args[0][0], "osascript")

    def test_send_imessage_failure_raises(self):
        proc = MagicMock()
        proc.returncode = 1
        proc.stdout = "nope"
        proc.stderr = ""

        with patch.object(gateway.subprocess, "run", return_value=proc):
            with self.assertRaises(RuntimeError) as ctx:
                gateway.send_imessage(to_handle="+15551234567", body="hi")

        self.assertIn("nope", str(ctx.exception))

    def test_claim_next_returns_none_on_204(self):
        res = MagicMock()
        res.status_code = 204

        with patch.object(gateway.requests, "post", return_value=res) as post_mock:
            out = gateway.claim_next(api_base_url="http://127.0.0.1:8000", gateway_id="mac-1")

        self.assertIsNone(out)
        post_mock.assert_called_once()

    def test_claim_next_parses_message(self):
        res = MagicMock()
        res.status_code = 200
        res.json.return_value = {
            "id": "123",
            "to_handle": "+15551234567",
            "body": "hi",
            "scheduled_for": "2025-12-16T00:00:00Z",
        }
        res.raise_for_status.return_value = None

        with patch.object(gateway.requests, "post", return_value=res):
            out = gateway.claim_next(api_base_url="http://127.0.0.1:8000", gateway_id="mac-1")

        self.assertIsNotNone(out)
        self.assertEqual(out.id, "123")
        self.assertEqual(out.to_handle, "+15551234567")
        self.assertEqual(out.body, "hi")

    def test_report_status_posts_payload(self):
        res = MagicMock()
        res.raise_for_status.return_value = None

        with patch.object(gateway.requests, "post", return_value=res) as post_mock:
            gateway.report_status(
                api_base_url="http://127.0.0.1:8000",
                message_id="123",
                status="SENT",
                error=None,
                detail={"gateway_id": "mac-1"},
            )

        post_mock.assert_called_once()
        _, kwargs = post_mock.call_args
        self.assertEqual(kwargs["json"]["message_id"], "123")
        self.assertEqual(kwargs["json"]["status"], "SENT")
        self.assertEqual(kwargs["json"]["detail"]["gateway_id"], "mac-1")

    @patch.dict(os.environ, {"API_BASE_URL": "http://127.0.0.1:8000", "GATEWAY_ID": "mac-1", "POLL_SECONDS": "0"})
    def test_main_happy_path_reports_sent(self):
        claimed = gateway.ClaimedMessage(
            id="123",
            to_handle="+15551234567",
            body="hi",
            scheduled_for="2025-12-16T00:00:00Z",
        )

        # First loop returns a message, second loop raises KeyboardInterrupt to stop
        claim_side_effect = [claimed, KeyboardInterrupt()]

        with patch.object(gateway, "load_dotenv", return_value=None), \
             patch.object(gateway, "claim_next", side_effect=claim_side_effect) as claim_mock, \
             patch.object(gateway, "send_imessage", return_value=None) as send_mock, \
             patch.object(gateway, "report_status", return_value=None) as report_mock, \
             patch.object(gateway.time, "sleep", return_value=None):
            with self.assertRaises(KeyboardInterrupt):
                gateway.main()

        claim_mock.assert_called()
        send_mock.assert_called_once_with(to_handle=claimed.to_handle, body=claimed.body)
        report_mock.assert_called_once()
        _, kwargs = report_mock.call_args
        self.assertEqual(kwargs["status"], "SENT")
        self.assertEqual(kwargs["message_id"], "123")

    @patch.dict(os.environ, {"API_BASE_URL": "http://127.0.0.1:8000", "GATEWAY_ID": "mac-1", "POLL_SECONDS": "0"})
    def test_main_failed_send_reports_failed(self):
        claimed = gateway.ClaimedMessage(
            id="123",
            to_handle="+15551234567",
            body="hi",
            scheduled_for="2025-12-16T00:00:00Z",
        )
        claim_side_effect = [claimed, KeyboardInterrupt()]

        with patch.object(gateway, "load_dotenv", return_value=None), \
             patch.object(gateway, "claim_next", side_effect=claim_side_effect), \
             patch.object(gateway, "send_imessage", side_effect=RuntimeError("boom")), \
             patch.object(gateway, "report_status", return_value=None) as report_mock, \
             patch.object(gateway.time, "sleep", return_value=None):
            with self.assertRaises(KeyboardInterrupt):
                gateway.main()

        report_mock.assert_called_once()
        _, kwargs = report_mock.call_args
        self.assertEqual(kwargs["status"], "FAILED")
        self.assertEqual(kwargs["message_id"], "123")
        self.assertIn("boom", kwargs["error"])


if __name__ == "__main__":
    unittest.main()
