"""Tests for the optional LLM explainer (stdlib unittest, no network)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from explainer import AI_LABEL, ENABLE_ENV, explain_flag, rule_explanation  # noqa: E402
from reconcile import Txn, analyze, parse_csv  # noqa: E402
from report import build_report  # noqa: E402

SAMPLE = """Date,Name,Type,Status,Currency,Gross,Fee,Net,Transaction ID
2026-10-01,Acme Corp,Payment,Completed,USD,100.00,-2.90,97.10,TXN001
2026-10-02,Acme Corp,Payment,Completed,USD,100.00,-2.90,97.10,TXN001
2026-10-05,Delta Co,Payment,Pending,USD,30.00,-0.90,29.10,TXN004
"""


class FakeClient:
    """Injected stand-in that records prompts and never touches the network."""

    def __init__(self, reply="The fee was recorded incorrectly and needs review."):
        self.reply = reply
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.reply


class FakeClassClient:
    def __init__(self):
        self.prompts = []

    def explain(self, prompt):
        self.prompts.append(prompt)
        return "Two rows share one transaction ID."


def _txn(flags, **overrides):
    defaults = dict(
        date="2026-10-01", name="Acme Corp", type="Payment", status="Completed",
        currency="USD", gross=100.0, fee=-2.9, net=97.1, txid="TXN001",
        category="Payment received", flags=list(flags),
    )
    defaults.update(overrides)
    return Txn(**defaults)


class TestExplainer(unittest.TestCase):
    def setUp(self):
        self.saved = os.environ.get(ENABLE_ENV)
        os.environ.pop(ENABLE_ENV, None)

    def tearDown(self):
        if self.saved is None:
            os.environ.pop(ENABLE_ENV, None)
        else:
            os.environ[ENABLE_ENV] = self.saved

    def test_rule_only_path_without_client(self):
        txn = _txn(["Duplicate transaction ID"])
        text = explain_flag("Duplicate transaction ID", txn)
        self.assertEqual(text, rule_explanation("Duplicate transaction ID", txn))
        self.assertNotIn(AI_LABEL, text)
        self.assertTrue(text.endswith("."))

    def test_off_by_default_ignores_available_client(self):
        txn = _txn(["Duplicate transaction ID"])
        client = FakeClient()
        text = explain_flag("Duplicate transaction ID", txn, client=client)
        self.assertEqual(client.prompts, [])  # never called
        self.assertEqual(text, rule_explanation("Duplicate transaction ID", txn))
        self.assertNotIn(AI_LABEL, text)

    def test_injected_callable_client_is_labeled(self):
        txn = _txn(["Duplicate transaction ID"])
        client = FakeClient()
        text = explain_flag(
            "Duplicate transaction ID", txn, client=client, enabled=True
        )
        self.assertTrue(text.startswith(AI_LABEL + ": "))
        self.assertIn("The fee was recorded incorrectly", text)
        self.assertEqual(len(client.prompts), 1)
        self.assertIn("Duplicate transaction ID", client.prompts[0])

    def test_env_variable_enables_injected_class_client(self):
        os.environ[ENABLE_ENV] = "1"
        txn = _txn(["Duplicate transaction ID"])
        client = FakeClassClient()
        text = explain_flag("Duplicate transaction ID", txn, client=client)
        self.assertTrue(text.startswith(AI_LABEL + ": "))
        self.assertEqual(text, AI_LABEL + ": Two rows share one transaction ID.")

    def test_failing_client_falls_back_to_rules(self):
        def boom(prompt):
            raise RuntimeError("no network here")

        txn = _txn(["Duplicate transaction ID"])
        text = explain_flag("Duplicate transaction ID", txn, client=boom,
                            enabled=True)
        self.assertEqual(text, rule_explanation("Duplicate transaction ID", txn))
        self.assertNotIn(AI_LABEL, text)

    def test_report_labels_ai_explanations(self):
        result = analyze(parse_csv(SAMPLE))
        report = build_report(result, client=FakeClient(), explainer_enabled=True)
        self.assertIn(AI_LABEL + ": The fee was recorded incorrectly", report)
        self.assertIn("<h2>Explanations</h2>", report)

    def test_report_default_has_no_ai_output(self):
        result = analyze(parse_csv(SAMPLE))
        report = build_report(result)
        self.assertNotIn(AI_LABEL, report)
        self.assertNotIn("Explanations</h2>", report)


if __name__ == "__main__":
    unittest.main()
