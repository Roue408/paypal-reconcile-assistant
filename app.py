"""PayPal Reconciliation Assistant: CLI + tiny web demo (stdlib only).

Usage:
    python3 app.py --csv samples/sample_transactions.csv --out out/report.html
    python3 app.py --serve --port 8000
    python3 app.py --sandbox --start 2026-10-01 --end 2026-10-29 --out out/report.html
    python3 app.py --csv samples/sample_transactions.csv --out out/report.html --ai

AI explanations (new in the top-3 improvements):
- OFF by default. The web form has an unchecked checkbox; the CLI needs
  --ai. Either way, AI runs only with an operator-provided Gemini key
  in GEMINI_API_KEY / GOOGLE_API_KEY, never hardcoded, never logged.
- AI text is always labeled "AI-generated" (see explainer.py). If the
  key is missing or the API fails, the report falls back to
  rule-based explanations and says so — it never fakes AI text.

Live PayPal (new in the top-3 improvements):
- --sandbox / the web "Fetch from PayPal sandbox" form pulls live
  sandbox transactions via paypal_client.py, then reconciles them
  with the same flag rules as the CSV path. Credentials come only
  from PAYPAL_SANDBOX_* env vars or the operator's local
  sandbox_config.json, never from chat or the repo.
- Default behaviour is unchanged: without --ai / --sandbox, the
  CSV path, flag rules, and report totals are exactly as before.
"""

import argparse
import html
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_client import GeminiClient  # noqa: E402
from explainer import is_enabled  # noqa: E402
from reconcile import analyze, explain, parse_csv  # noqa: E402
from report import build_report  # noqa: E402

FORM = """<html><head><meta charset='utf-8'><title>PayPal reconciliation</title></head>
<body><h1>PayPal reconciliation assistant</h1>
<p>Paste a PayPal activity-export CSV below. Nothing is sent anywhere; the
report is generated locally. <a href='/sample'>See sample CSV</a>.</p>
<form method='post' action='/reconcile'>
<textarea name='csv' rows='20' cols='100' placeholder='Date,Name,Type,Status,Currency,Gross,Fee,Net,Transaction ID...'></textarea>
<br><label><input type='checkbox' name='ai' value='1'>
AI explanations (needs your Gemini key in the environment, off by default; AI text is labeled)</label>
<br><input type='submit' value='Reconcile'>
</form>
<h2>Or fetch live from the PayPal sandbox</h2>
<p>Uses your sandbox credentials only (env vars or your local
sandbox_config.json). Nothing is sent anywhere except PayPal's sandbox API.</p>
<form method='post' action='/sandbox'>
Start: <input name='start' value='2026-10-01'> End: <input name='end' value='2026-10-29'>
<label><input type='checkbox' name='ai' value='1'> AI explanations</label>
<input type='submit' value='Fetch sandbox transactions'>
</form></body></html>"""


def _ai_client_or_notice(ai_requested):
    """Return (client, explainer_enabled, notice).

    AI is on only when requested AND a client can be built. Otherwise
    the caller shows rule-based explanations plus the notice, so a
    missing key is never silently presented as AI.
    """
    if not ai_requested:
        return None, False, ""
    try:
        return GeminiClient(), True, ""
    except Exception as exc:
        return None, False, (
            "AI explanations unavailable (%s) — showing rule-based "
            "explanations instead." % exc
        )


def _report_html(result, ai_requested):
    client, ai_on, notice = _ai_client_or_notice(ai_requested)
    body = build_report(result, client=client, explainer_enabled=ai_on)
    if notice:
        body = body.replace(
            "</body>", "<p><em>%s</em></p></body>" % html.escape(notice)
        )
    if not ai_on:
        explanations = "<h2>Explanations (rule-based)</h2><ul>" + "".join(
            "<li>" + html.escape(explain(t)) + "</li>" for t in result["transactions"]
        ) + "</ul>"
        body = body.replace("</body>", explanations + "</body>")
    return body


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, status=200, content_type="text/html; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/sample":
            here = os.path.dirname(os.path.abspath(__file__))
            with open(os.path.join(here, "samples", "sample_transactions.csv")) as handle:
                self._send("<pre>" + html.escape(handle.read()) + "</pre>")
        else:
            self._send(FORM)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        fields = parse_qs(self.rfile.read(length).decode("utf-8"))
        ai_requested = fields.get("ai", [""])[0] == "1"
        if self.path == "/reconcile":
            text = fields.get("csv", [""])[0]
            result = analyze(parse_csv(text))
            self._send(_report_html(result, ai_requested))
            return
        if self.path == "/sandbox":
            start = fields.get("start", [""])[0]
            end = fields.get("end", [""])[0]
            try:
                from paypal_client import fetch_live_transactions

                txns = fetch_live_transactions(
                    start + "T00:00:00Z", end + "T23:59:59Z"
                )
            except Exception as exc:
                # Error text never contains a credential value: see
                # paypal_client.py (MissingCredentialsError message).
                self._send(
                    "<p>Live sandbox fetch failed: %s</p><p><a href='/'>Back</a></p>"
                    % html.escape(str(exc)),
                    status=502,
                )
                return
            result = analyze(txns)
            self._send(_report_html(result, ai_requested))
            return
        self._send("Not found", status=404)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", help="input PayPal CSV file")
    parser.add_argument("--out", help="output HTML report file")
    parser.add_argument("--serve", action="store_true", help="run web demo")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ai", action="store_true",
                        help="AI explanations (needs GEMINI_API_KEY, off by default)")
    parser.add_argument("--sandbox", action="store_true",
                        help="fetch live sandbox transactions instead of a CSV")
    parser.add_argument("--start", help="sandbox start date YYYY-MM-DD")
    parser.add_argument("--end", help="sandbox end date YYYY-MM-DD")
    args = parser.parse_args()
    if args.serve:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
        print("Serving on http://127.0.0.1:%d (Ctrl-C to stop)" % args.port)
        server.serve_forever()
        return
    if not args.out:
        parser.error("--out is required unless --serve is given")
    if args.sandbox:
        if not args.start or not args.end:
            parser.error("--sandbox requires --start and --end")
        from paypal_client import fetch_live_transactions

        txns = fetch_live_transactions(
            args.start + "T00:00:00Z", args.end + "T23:59:59Z"
        )
        result = analyze(txns)
        source = "sandbox"
    else:
        if not args.csv:
            parser.error("--csv is required unless --serve or --sandbox is given")
        with open(args.csv, encoding="utf-8-sig") as handle:
            result = analyze(parse_csv(handle.read()))
        source = "csv"
    client, ai_on, notice = _ai_client_or_notice(args.ai)
    if notice:
        print("Warning: %s" % notice, file=sys.stderr)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(build_report(result, client=client, explainer_enabled=ai_on))
    print("Wrote %s from %s: %d transactions, %d flagged, total net %.2f"
          % (args.out, source, len(result["transactions"]), len(result["flagged"]),
             result["total_net"]))


def log_message(self, *args):
    pass


Handler.log_message = log_message


if __name__ == "__main__":
    main()
