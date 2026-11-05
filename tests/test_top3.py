"""Tests for the top-3 improvements: AI in the demo, live PayPal in the demo.

No network, no real keys, no real PayPal data. The Gemini client is
tested with a fake urlopen; the sandbox fetch is tested by mocking
the two live-call functions in paypal_client.
"""

import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_client import GeminiClient  # noqa: E402
from app import _ai_client_or_notice, _report_html  # noqa: E402
from reconcile import Txn, analyze  # noqa: E402


def _fake_response(payload):
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    return Resp()


class TestGeminiClient(unittest.TestCase):
    def test_returns_text(self):
        def fake_urlopen(request, timeout=30):
            return _fake_response(
                {"candidates": [{"content": {"parts": [{"text": "AI says hello."}]}}]}
            )

        client = GeminiClient(api_key="test-key-only", urlopen=fake_urlopen)
        self.assertEqual(client.explain("prompt"), "AI says hello.")

    def test_no_text_raises_so_caller_falls_back(self):
        def fake_urlopen(request, timeout=30):
            return _fake_response({"candidates": []})

        client = GeminiClient(api_key="test-key-only", urlopen=fake_urlopen)
        with self.assertRaises(RuntimeError):
            client.explain("prompt")

    def test_no_key_raises_without_leaking(self):
        with self.assertRaises(RuntimeError):
            GeminiClient(api_key="")


class TestAIInReport(unittest.TestCase):
    def _result(self):
        txn = Txn(date="2026-10-01", name="Shop", type="Payment",
                  status="Completed", currency="USD", gross=100.0,
                  fee=3.0, net=90.0, txid="T1")
        txn.category = "Payment received"
        txn.flags = ["Net does not match Gross minus Fee"]
        return analyze([txn])

    def test_ai_label_present_when_client_works(self):
        class Client:
            def explain(self, prompt):
                return "This looks like a missing adjustment."

        # Build via build_report directly to avoid the web helper's
        # client-construction path (which needs a real key).
        from report import build_report

        out = build_report(self._result(), client=Client(), explainer_enabled=True)
        self.assertIn("AI-generated: This looks like a missing adjustment.", out)

    def test_failing_client_falls_back_to_rules(self):
        class BadClient:
            def explain(self, prompt):
                raise RuntimeError("boom")

        from report import build_report

        out = build_report(self._result(), client=BadClient(), explainer_enabled=True)
        self.assertNotIn("AI-generated", out)
        self.assertIn("does not equal gross", out)

    def test_ai_not_requested_means_no_ai_section(self):
        client, ai_on, notice = _ai_client_or_notice(False)
        self.assertIsNone(client)
        self.assertFalse(ai_on)
        self.assertEqual(notice, "")


class TestLiveSandboxInDemo(unittest.TestCase):
    def test_fetch_live_maps_mocked_api_response(self):
        import paypal_client

        canned = {
            "transaction_details": [
                {
                    "transaction_info": {
                        "transaction_id": "S1",
                        "transaction_initiation_date": "2026-10-02T10:00:00Z",
                        "transaction_status": "S",
                        "transaction_subject": "Payment",
                        "transaction_amount": {"value": "50.00", "currency_code": "USD"},
                        "fee_amount": {"value": "1.50", "currency_code": "USD"},
                    },
                    "payer_info": {"email_address": "buyer@example.test"},
                }
            ]
        }
        with mock.patch.object(paypal_client, "get_access_token", return_value="tok"), \
             mock.patch.object(paypal_client, "search_transactions", return_value=canned), \
             mock.patch.object(paypal_client, "load_credentials",
                               return_value=("id", "secret")):
            txns = paypal_client.fetch_live_transactions(
                "2026-10-01T00:00:00Z", "2026-10-29T23:59:59Z"
            )
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].txid, "S1")
        self.assertEqual(txns[0].status, "Completed")
        result = analyze(txns)
        self.assertEqual(result["total_net"], 48.50)


if __name__ == "__main__":
    unittest.main()
