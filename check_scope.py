"""Check whether the sandbox token carries the Transaction Search scope.

Usage (on the laptop, in the paypal-app folder):
    python check_scope.py

Prints ONLY the scope list PayPal returns for the token — never the
token itself and never the client ID/secret. If the list contains
    https://uri.paypal.com/services/reporting/search/read
the app has the Transaction Search permission and the 403 is a
propagation/account problem, not a missing checkbox. If it is absent,
Transaction Search is not enabled on the sandbox app yet (or the
change has not taken effect — PayPal notes say up to ~9 hours).
"""

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from paypal_client import (  # noqa: E402
    SANDBOX_BASE,
    MissingCredentialsError,
    basic_auth_header,
    load_credentials,
)

REPORTING_SCOPE = "https://uri.paypal.com/services/reporting/search/read"


def main():
    try:
        client_id, client_secret = load_credentials()
    except MissingCredentialsError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    request = urllib.request.Request(
        SANDBOX_BASE + "/v1/oauth2/token",
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": basic_auth_header(client_id, client_secret),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # HTTPError/URLError: token step failed
        print("Token step failed: %s" % exc, file=sys.stderr)
        return 3
    scopes = (payload.get("scope", "") or "").split()
    print("Token scopes:")
    for scope in scopes:
        print("  " + scope)
    if REPORTING_SCOPE in scopes:
        print("Transaction Search scope: PRESENT — the permission is on "
              "the token. A 403 now means propagation or an account-level "
              "block, not a missing checkbox.")
    else:
        print("Transaction Search scope: MISSING — Transaction Search is "
              "not enabled on the sandbox app yet, or the change has not "
              "taken effect yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
