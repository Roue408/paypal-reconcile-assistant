# PayPal Reconciliation Assistant — hackathon prototype

Paste in a messy PayPal transaction export (CSV) and get categorized, explained,
discrepancy-flagged output plus an HTML report. Python standard library only.

## Run

CLI (writes an HTML report):

    python3 app.py --csv samples/sample_transactions.csv --out out/report.html

Web demo (paste CSV into the form):

    python3 app.py --serve --port 8000

Tests:

    python3 -m unittest discover -s tests -v

## What it does now

- Flexible CSV header matching (PayPal activity-export columns).
- Categorization: payments received/sent, refunds, reversals, subscriptions,
  withdrawals, deposits, holds, fees, other.
- Discrepancy flags: net != gross minus fee, duplicate transaction IDs,
  non-completed statuses, fees over 10% of gross.
- Rule-based one-line explanations per transaction (labeled as rule-based).

## Still TODO before submission (due Nov 12, 2026, 12:00 PM PT)

- PayPal Sandbox integration — WIRED 2026-10-29: sandbox Developer account
  signed in; sandbox Business + Personal test accounts present; REST API app
  "AI Hackathon - Reconcile Assistant" created. `fetch_sandbox.py` pulls live
  sandbox transactions into a CSV the report already consumes
  (`python3 fetch_sandbox.py --start 2026-10-01 --end 2026-10-29 --out
  out/sandbox_transactions.csv`). Remaining: paste the sandbox app's client
  ID and secret into a local `sandbox_config.json` (copy from
  `sandbox_config.example.json`; gitignored, never committed or shared) or
  set the PAYPAL_SANDBOX_* env vars, then run the fetch and confirm the
  Transaction Search scope returns data. Event-code → category refinement
  still needs real sandbox data.
- AI feature: DONE 2026-11-02 — `ai_client.py` (stdlib Gemini client)
  wired into the CLI (--ai) and web demo (checkbox), behind an
  operator-provided GEMINI_API_KEY, off by default. AI text is
  labeled "AI-generated"; missing key or API failure falls back
  to rule-based explanations with a notice.
- Demo video under 3 minutes showing the working app in the first 30 seconds:
  script ready in VIDEO-SCRIPT.md (90-second real screen recording);
  recording + public YouTube upload are operator steps.
- Public repo with license + README (entry must be public/open-source; this
  tool can never be sold closed later — accepted for this entry only).
- Read the Devpost rules-tab license grant before submitting (unverified).

## Notes

Sample data is fictional. This tool reads exports the operator provides; it does
not move money and never needs PayPal credentials for the CSV path.
