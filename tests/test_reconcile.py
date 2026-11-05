"""Tests for the PayPal reconciliation core (stdlib unittest)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reconcile import analyze, explain, parse_csv  # noqa: E402

SAMPLE = """Date,Name,Type,Status,Currency,Gross,Fee,Net,Transaction ID
2026-10-01,Acme Corp,Payment,Completed,USD,100.00,-2.90,97.10,TXN001
2026-10-02,Acme Corp,Payment,Completed,USD,100.00,-2.90,97.10,TXN001
2026-10-03,Beta LLC,Refund,Completed,USD,-50.00,0.00,-50.00,TXN002
2026-10-04,Gamma Inc,Payment,Completed,USD,20.00,-0.50,19.00,TXN003
2026-10-05,Delta Co,Payment,Pending,USD,30.00,-0.90,29.10,TXN004
"""


class TestReconcile(unittest.TestCase):
    def setUp(self):
        self.result = analyze(parse_csv(SAMPLE))

    def test_parses_all_rows(self):
        self.assertEqual(len(self.result["transactions"]), 5)

    def test_categories(self):
        categories = [t.category for t in self.result["transactions"]]
        self.assertEqual(categories.count("Payment received"), 4)
        self.assertEqual(categories.count("Refund"), 1)

    def test_total_net(self):
        self.assertAlmostEqual(self.result["total_net"], 192.30, places=2)

    def test_flags(self):
        flagged = self.result["flagged"]
        self.assertEqual(len(flagged), 3)
        all_flags = "; ".join(f for t in flagged for f in t.flags)
        self.assertIn("Duplicate transaction ID", all_flags)
        self.assertIn("Net does not match Gross minus Fee", all_flags)
        self.assertIn("Pending", all_flags)

    def test_explain_mentions_flags(self):
        flagged = self.result["flagged"][0]
        self.assertIn("Attention", explain(flagged))


if __name__ == "__main__":
    unittest.main()
