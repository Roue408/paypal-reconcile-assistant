"""PayPal Sandbox client (Python standard library only).

Wiring status (2026-10-29): the sandbox account and REST API app exist
("AI Hackathon - Reconcile Assistant", sandbox Merchant app), so live calls
are wired but still need the operator's sandbox credentials, which are never
stored in this repo. Credentials come from environment variables
PAYPAL_SANDBOX_CLIENT_ID / PAYPAL_SANDBOX_CLIENT_SECRET, or from a local
sandbox_config.json (gitignored, see sandbox_config.example.json).
What IS tested without credentials is the response-mapping logic, against
a canned Transaction Search fixture.

Endpoints (PayPal REST, sandbox base https://api-m.sandbox.paypal.com):
- POST /v1/oauth2/token (grant_type=client_credentials, HTTP Basic auth)
- GET  /v1/reporting/transactions?start_date=...&end_date=...&fields=all

Mapping notes, stated plainly:
- Status codes mapped: S -> Completed, P -> Pending. Any other code is kept
  raw, because its meaning was not verified against live data.
- The transaction type is the event code / subject as returned. Refining
  event-code -> category mapping is a build task once real sandbox data is
  available; until then, unknown types categorize as Other via reconcile.py.
- Net is computed as gross minus the absolute fee, matching reconcile.py's
  arithmetic check.
"""

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from reconcile import Txn, categorize

SANDBOX_BASE = "https://api-m.sandbox.paypal.com"

STATUS_MAP = {"S": "Completed", "P": "Pending"}


def basic_auth_header(client_id, client_secret):
    token = base64.b64encode(
        ("%s:%s" % (client_id, client_secret)).encode("utf-8")
    ).decode("ascii")
    return "Basic " + token


def get_access_token(base_url, client_id, client_secret):
    """Exchange client credentials for an access token. Live call, untested."""
    request = urllib.request.Request(
        base_url + "/v1/oauth2/token",
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": basic_auth_header(client_id, client_secret),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))["access_token"]


def search_transactions(base_url, access_token, start_date, end_date):
    """Fetch raw Transaction Search JSON. Live call, untested."""
    query = urllib.parse.urlencode(
        {"start_date": start_date, "end_date": end_date, "fields": "all"}
    )
    request = urllib.request.Request(
        base_url + "/v1/reporting/transactions?" + query,
        headers={"Authorization": "Bearer " + access_token},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def map_transaction(detail):
    """Map one transaction_details entry to a Txn. Pure function, tested."""
    info = detail.get("transaction_info", {}) or {}
    payer = detail.get("payer_info", {}) or {}
    payer_name = payer.get("payer_name", {}) or {}
    amount = info.get("transaction_amount", {}) or {}
    fee = info.get("fee_amount", {}) or {}
    gross = float(amount.get("value", 0) or 0)
    fee_value = float(fee.get("value", 0) or 0)
    net = gross - abs(fee_value)
    status_code = info.get("transaction_status", "")
    txn = Txn(
        date=(info.get("transaction_initiation_date", "") or "")[:10],
        name=payer_name.get("alternate_full_name", "") or payer.get("email_address", ""),
        type=info.get("transaction_subject", "") or info.get("transaction_event_code", ""),
        status=STATUS_MAP.get(status_code, status_code),
        currency=amount.get("currency_code", ""),
        gross=gross,
        fee=fee_value,
        net=net,
        txid=info.get("transaction_id", ""),
    )
    txn.category = categorize(txn)
    return txn


class MissingCredentialsError(RuntimeError):
    """Raised when no sandbox credentials are available. Message never
    contains a credential value."""


class PayPalApiError(RuntimeError):
    """A PayPal HTTP error with the step that failed, so the operator can
    tell a token-step failure from a search-step failure. Carries only
    PayPal's public error fields (name/message/debug_id) — never request
    headers, which carry credentials."""

    def __init__(self, step, status, name="", message="", debug_id=""):
        self.step = step
        self.status = status
        self.name = name
        self.message = message
        self.debug_id = debug_id
        super().__init__(
            "PayPal %s step failed: HTTP %s %s"
            % (step, status, (name + ": " + message).strip())
        )


def _api_error(step, exc):
    """Build a PayPalApiError from a urllib HTTPError, reading only the
    response body (never headers). Falls back to the HTTP reason."""
    status = getattr(exc, "code", "?")
    name = message = debug_id = ""
    try:
        body = exc.read().decode("utf-8", errors="replace")
        data = json.loads(body) if body else {}
        if isinstance(data, dict):
            name = str(data.get("name", "") or "")
            message = str(data.get("message", "") or "")
            debug_id = str(data.get("debug_id", "") or "")
            details = data.get("details")
            if not message and isinstance(details, list) and details:
                message = str(details[0].get("issue", "") or "")
    except Exception:
        pass
    if not name and not message:
        message = str(getattr(exc, "reason", "") or "")
    return PayPalApiError(step, status, name, message, debug_id)


def _usable(value):
    """Return the stripped value, or "" when it is empty, whitespace-only,
    or still an unreplaced PASTE_ placeholder from the example config.

    Placeholders must never be treated as credentials: before this fix,
    the shipped sandbox_config.json (placeholder-only) was returned as
    if real, so a fetch burned a live call and failed with a confusing
    HTTP 401 instead of the clean missing-credentials message.
    """
    text = str(value or "").strip()
    if not text or text.upper().startswith("PASTE_"):
        return ""
    return text


def load_credentials(config_path=None):
    """Load sandbox credentials without ever printing them.

    Order: environment variables first, then sandbox_config.json next to
    this file. A source counts only when BOTH values are present and
    usable; a half-set env pair falls through to the config file, and
    placeholder/malformed config is treated as missing, not as credentials.
    Returns (client_id, client_secret). Raises MissingCredentialsError
    with setup instructions when neither source is usable.
    """
    import os

    client_id = _usable(os.environ.get("PAYPAL_SANDBOX_CLIENT_ID", ""))
    client_secret = _usable(os.environ.get("PAYPAL_SANDBOX_CLIENT_SECRET", ""))
    if client_id and client_secret:
        return client_id, client_secret
    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "sandbox_config.json"
        )
    try:
        with open(config_path, encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("sandbox config is not a JSON object")
        client_id = _usable(data.get("client_id", ""))
        client_secret = _usable(data.get("client_secret", ""))
        if client_id and client_secret:
            return client_id, client_secret
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    raise MissingCredentialsError(
        "No PayPal sandbox credentials found. Set environment variables "
        "PAYPAL_SANDBOX_CLIENT_ID and PAYPAL_SANDBOX_CLIENT_SECRET, or copy "
        "sandbox_config.example.json to sandbox_config.json and paste the "
        "sandbox app's client ID and secret into it. Never put credentials "
        "in chat, in the repo, or in any shared file."
    )


def fetch_live_transactions(start_date, end_date, base_url=SANDBOX_BASE):
    """Live sandbox fetch: OAuth token + Transaction Search + mapping.

    start_date/end_date are ISO-8601 strings (e.g. 2026-10-01T00:00:00Z).
    Returns a list of Txn. Needs credentials from load_credentials().
    """
    client_id, client_secret = load_credentials()
    try:
        token = get_access_token(base_url, client_id, client_secret)
    except urllib.error.HTTPError as exc:
        raise _api_error("token", exc)
    except urllib.error.URLError as exc:
        raise PayPalApiError("token", "?", "", str(exc.reason or exc))
    try:
        payload = search_transactions(base_url, token, start_date, end_date)
    except urllib.error.HTTPError as exc:
        raise _api_error("search", exc)
    except urllib.error.URLError as exc:
        raise PayPalApiError("search", "?", "", str(exc.reason or exc))
    return [map_transaction(d) for d in payload.get("transaction_details", [])]
