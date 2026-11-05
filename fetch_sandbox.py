"""Fetch live sandbox transactions and write a reconcile-ready CSV.

Usage:
    python3 fetch_sandbox.py --start 2026-10-01 --end 2026-10-29 --out out/sandbox_transactions.csv

Credentials are NOT arguments and are never printed: set environment
variables PAYPAL_SANDBOX_CLIENT_ID / PAYPAL_SANDBOX_CLIENT_SECRET, or copy
sandbox_config.example.json to sandbox_config.json and paste the sandbox
app's client ID and secret into that local file (it is gitignored and must
never be committed or shared). Then run the report on the fetched CSV:

    python3 app.py --csv out/sandbox_transactions.csv --out out/report.html
"""

import argparse
import csv
import datetime
import os
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from paypal_client import MissingCredentialsError, PayPalApiError, fetch_live_transactions  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="end date YYYY-MM-DD")
    parser.add_argument("--out", required=True, help="output CSV file")
    args = parser.parse_args()
    try:
        start_day = datetime.date.fromisoformat(args.start)
        end_day = datetime.date.fromisoformat(args.end)
    except ValueError:
        print("Dates must be YYYY-MM-DD, e.g. --start 2026-10-05 --end 2026-11-04",
              file=sys.stderr)
        return 2
    if (end_day - start_day).days > 30:
        print("Date range is %d days; PayPal Transaction Search allows at most "
              "31 days. Use a shorter range, e.g. --start 2026-10-05 "
              "--end 2026-11-04." % ((end_day - start_day).days + 1),
              file=sys.stderr)
        return 2
    start = args.start + "T00:00:00Z"
    end = args.end + "T23:59:59Z"
    try:
        txns = fetch_live_transactions(start, end)
    except MissingCredentialsError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except PayPalApiError as exc:
        print("Live sandbox call failed at the %s step: HTTP %s %s"
              % (exc.step, exc.status,
                 (exc.name + ": " + exc.message).strip()), file=sys.stderr)
        if exc.debug_id:
            print("PayPal debug_id: %s" % exc.debug_id, file=sys.stderr)
        if exc.step == "search" and str(exc.status) == "403":
            print("This is usually the Transaction Search permission: in the "
                  "PayPal Developer Dashboard, Sandbox tab, open the app and "
                  "make sure Transaction Search is enabled for it, then run "
                  "the fetch again for a fresh token.", file=sys.stderr)
        elif exc.step == "token":
            print("The token step failed, so the client ID/secret pair was "
                  "not accepted for the sandbox app — re-copy both from the "
                  "Sandbox tab of that app, in one go.", file=sys.stderr)
        return 3
    except urllib.error.URLError as exc:
        # HTTPError str is "HTTP Error <code>: <reason>" only; request
        # headers (which carry the credentials) are never printed.
        print("Live sandbox call failed: %s. If this is a 401, the "
              "sandbox client ID/secret do not match the sandbox app "
              "- re-copy them from the app in the PayPal Developer "
              "Dashboard and try again. Credentials are never printed "
              "here." % exc, file=sys.stderr)
        return 3
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "Name", "Type", "Status", "Currency",
                         "Gross", "Fee", "Net", "Transaction ID"])
        for txn in txns:
            writer.writerow([txn.date, txn.name, txn.type, txn.status,
                             txn.currency, "%.2f" % txn.gross,
                             "%.2f" % txn.fee, "%.2f" % txn.net, txn.txid])
    print("Fetched %d sandbox transactions -> %s" % (len(txns), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
