"""Tests for the PayPal Sandbox client mapping (stdlib unittest)."""

import base64
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paypal_client import basic_auth_header, map_transaction  # noqa: E402

FIXTURE = {
    "transaction_info": {
        "transaction_id": "SANDBOX001",
        "transaction_event_code": "T0000",
        "transaction_initiation_date": "2026-10-20T10:00:00+0000",
        "transaction_amount": {"currency_code": "USD", "value": "25.00"},
        "fee_amount": {"currency_code": "USD", "value": "-0.85"},
        "transaction_status": "S",
        "transaction_subject": "Payment",
    },
    "payer_info": {
        "payer_name": {"alternate_full_name": "Sample Buyer"},
        "email_address": "buyer@example.com",
    },
}


class TestPayPalClient(unittest.TestCase):
    def test_basic_auth_header(self):
        header = basic_auth_header("myid", "mysecret")
        self.assertEqual(
            header, "Basic " + base64.b64encode(b"myid:mysecret").decode("ascii")
        )

    def test_map_transaction(self):
        txn = map_transaction(FIXTURE)
        self.assertEqual(txn.txid, "SANDBOX001")
        self.assertEqual(txn.date, "2026-10-20")
        self.assertEqual(txn.name, "Sample Buyer")
        self.assertEqual(txn.currency, "USD")
        self.assertAlmostEqual(txn.gross, 25.00, places=2)
        self.assertAlmostEqual(txn.fee, -0.85, places=2)
        self.assertAlmostEqual(txn.net, 24.15, places=2)
        self.assertEqual(txn.status, "Completed")

    def test_unknown_status_kept_raw(self):
        detail = {
            "transaction_info": {
                "transaction_id": "X",
                "transaction_status": "Q",
                "transaction_amount": {"currency_code": "USD", "value": "1.00"},
            }
        }
        self.assertEqual(map_transaction(detail).status, "Q")


if __name__ == "__main__":
    unittest.main()
