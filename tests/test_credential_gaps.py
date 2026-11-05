"""Tests for credential-loading gaps found 2026-10-29 (all values fake).

Gap 1 (confirmed live): the shipped sandbox_config.json was still
placeholder-only, yet load_credentials() returned its PASTE_ values as
if real, so fetch_sandbox.py burned a live call and died with a bare
HTTP 401 traceback (exit 1) instead of the clean exit-2 instructions.
Gap 2: a non-object JSON config (list/string) raised AttributeError
instead of MissingCredentialsError. Gap 3: fetch_sandbox.py had no
handling for HTTP/network failures at all. Gap 4 (checked, no fix
needed): the fetch CSV header must round-trip through reconcile's
flexible parser with no false net-mismatch flag.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fetch_sandbox  # noqa: E402
from paypal_client import MissingCredentialsError, load_credentials, map_transaction  # noqa: E402
from reconcile import analyze, parse_csv  # noqa: E402


def _write_temp(text):
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    handle.write(text)
    handle.close()
    return handle.name


class TestCredentialGaps(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in
                      ("PAYPAL_SANDBOX_CLIENT_ID", "PAYPAL_SANDBOX_CLIENT_SECRET")}
        os.environ.pop("PAYPAL_SANDBOX_CLIENT_ID", None)
        os.environ.pop("PAYPAL_SANDBOX_CLIENT_SECRET", None)
        self._temps = []

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for path in self._temps:
            try:
                os.unlink(path)
            except OSError:
                pass

    def _temp(self, text):
        path = _write_temp(text)
        self._temps.append(path)
        return path

    def test_placeholder_config_is_missing_not_credentials(self):
        path = self._temp(json.dumps({
            "client_id": "PASTE_SANDBOX_CLIENT_ID_HERE",
            "client_secret": "PASTE_SANDBOX_CLIENT_SECRET_HERE",
        }))
        with self.assertRaises(MissingCredentialsError) as ctx:
            load_credentials(path)
        self.assertNotIn("PASTE_", str(ctx.exception))

    def test_placeholder_env_vars_are_missing(self):
        os.environ["PAYPAL_SANDBOX_CLIENT_ID"] = "PASTE_SANDBOX_CLIENT_ID_HERE"
        os.environ["PAYPAL_SANDBOX_CLIENT_SECRET"] = "PASTE_SANDBOX_CLIENT_SECRET_HERE"
        with self.assertRaises(MissingCredentialsError):
            load_credentials("/nonexistent-dir/sandbox_config.json")

    def test_placeholder_env_falls_through_to_valid_file(self):
        os.environ["PAYPAL_SANDBOX_CLIENT_ID"] = "PASTE_SANDBOX_CLIENT_ID_HERE"
        os.environ["PAYPAL_SANDBOX_CLIENT_SECRET"] = "PASTE_SANDBOX_CLIENT_SECRET_HERE"
        path = self._temp(json.dumps({"client_id": "file-id-fake",
                                      "client_secret": "file-secret-fake"}))
        self.assertEqual(load_credentials(path),
                         ("file-id-fake", "file-secret-fake"))

    def test_partial_env_falls_through_to_valid_file(self):
        os.environ["PAYPAL_SANDBOX_CLIENT_ID"] = "only-one-side-fake"
        path = self._temp(json.dumps({"client_id": "file-id-fake",
                                      "client_secret": "file-secret-fake"}))
        self.assertEqual(load_credentials(path),
                         ("file-id-fake", "file-secret-fake"))

    def test_malformed_and_non_object_config_is_missing(self):
        for text in ("{not json", "[1, 2]", '"just a string"', "null"):
            with self.assertRaises(MissingCredentialsError, msg=text):
                load_credentials(self._temp(text))

    def test_whitespace_only_values_are_missing(self):
        path = self._temp(json.dumps({"client_id": "   ",
                                      "client_secret": "\n"}))
        with self.assertRaises(MissingCredentialsError):
            load_credentials(path)

    def test_error_message_never_contains_a_supplied_value(self):
        sentinel = "sentinel-half-set-fake-value-1"
        os.environ["PAYPAL_SANDBOX_CLIENT_ID"] = sentinel
        with self.assertRaises(MissingCredentialsError) as ctx:
            load_credentials("/nonexistent-dir/sandbox_config.json")
        self.assertNotIn(sentinel, str(ctx.exception))

    def test_fetch_csv_header_round_trips_through_reconciler(self):
        # Row built exactly as fetch_sandbox.py formats it.
        txn = map_transaction({
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
        })
        text = ("Date,Name,Type,Status,Currency,Gross,Fee,Net,Transaction ID\n"
                "%s,%s,%s,%s,%s,%.2f,%.2f,%.2f,%s\n"
                % (txn.date, txn.name, txn.type, txn.status, txn.currency,
                   txn.gross, txn.fee, txn.net, txn.txid))
        parsed = parse_csv(text)
        self.assertEqual(len(parsed), 1)
        row = parsed[0]
        self.assertEqual((row.date, row.name, row.type, row.status,
                          row.currency, row.txid),
                         ("2026-10-20", "Sample Buyer", "Payment",
                          "Completed", "USD", "SANDBOX001"))
        self.assertAlmostEqual(row.net, 24.15, places=2)
        result = analyze(parsed)
        self.assertEqual(
            [f for f in row.flags if "Net does not match" in f], [])


class TestFetchSandboxExitPaths(unittest.TestCase):
    def setUp(self):
        self.saved_argv = sys.argv
        self.saved_fn = fetch_sandbox.fetch_live_transactions

    def tearDown(self):
        sys.argv = self.saved_argv
        fetch_sandbox.fetch_live_transactions = self.saved_fn

    def _run_main(self):
        sys.argv = ["fetch_sandbox.py", "--start", "2026-10-01",
                    "--end", "2026-10-29", "--out", "out/probe.csv"]
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = fetch_sandbox.main()
        return code, err.getvalue()

    def test_missing_credentials_exits_2_with_instructions(self):
        fetch_sandbox.fetch_live_transactions = lambda s, e: (_ for _ in ()).throw(
            MissingCredentialsError("No PayPal sandbox credentials found."))
        code, err = self._run_main()
        self.assertEqual(code, 2)
        self.assertIn("credentials", err)

    def test_http_failure_exits_3_without_headers(self):
        def boom(start, end):
            raise urllib.error.HTTPError(
                "https://api-m.sandbox.paypal.com/v1/oauth2/token",
                401, "Unauthorized", None, None)
        fetch_sandbox.fetch_live_transactions = boom
        code, err = self._run_main()
        self.assertEqual(code, 3)
        self.assertIn("401", err)
        self.assertNotIn("Authorization", err)
        self.assertNotIn("Basic ", err)


if __name__ == "__main__":
    unittest.main()
