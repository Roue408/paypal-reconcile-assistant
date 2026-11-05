"""Tests for sandbox credential loading (no real credentials involved)."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paypal_client import MissingCredentialsError, load_credentials  # noqa: E402


class TestSandboxCredentials(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in
                      ("PAYPAL_SANDBOX_CLIENT_ID", "PAYPAL_SANDBOX_CLIENT_SECRET")}
        os.environ.pop("PAYPAL_SANDBOX_CLIENT_ID", None)
        os.environ.pop("PAYPAL_SANDBOX_CLIENT_SECRET", None)

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_env_vars_win(self):
        os.environ["PAYPAL_SANDBOX_CLIENT_ID"] = "env-id"
        os.environ["PAYPAL_SANDBOX_CLIENT_SECRET"] = "env-secret"
        self.assertEqual(load_credentials(), ("env-id", "env-secret"))

    def test_config_file_fallback(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as handle:
            json.dump({"client_id": "file-id",
                       "client_secret": "file-secret"}, handle)
            path = handle.name
        try:
            self.assertEqual(load_credentials(path), ("file-id", "file-secret"))
        finally:
            os.unlink(path)

    def test_missing_raises_clean_instructions(self):
        with self.assertRaises(MissingCredentialsError) as ctx:
            load_credentials("/nonexistent-dir/sandbox_config.json")
        message = str(ctx.exception)
        self.assertIn("sandbox_config", message)
        self.assertIn("PAYPAL_SANDBOX_CLIENT_ID", message)

    def test_example_file_has_placeholders_only(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(here, "sandbox_config.example.json")) as handle:
            data = json.load(handle)
        self.assertIn("PASTE_", data["client_id"])
        self.assertIn("PASTE_", data["client_secret"])


if __name__ == "__main__":
    unittest.main()
