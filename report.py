"""HTML report for the PayPal reconciliation assistant (stdlib only)."""

import html

from explainer import explain_flag, is_enabled

STYLE = """
body { font-family: sans-serif; max-width: 900px; margin: 2em auto; padding: 0 1em; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: left; }
th { background: #eee; }
.flag { color: #a00; font-weight: bold; }
"""


def _money(value):
    return "%.2f" % value


def build_report(result, client=None, explainer_enabled=None):
    esc = html.escape
    ai_active = is_enabled() if explainer_enabled is None else bool(explainer_enabled)
    parts = [
        "<html><head><meta charset='utf-8'><title>PayPal reconciliation</title>",
        "<style>" + STYLE + "</style></head><body>",
        "<h1>PayPal reconciliation report</h1>",
        "<p>Transactions: %d. Flagged for attention: %d. Total net: %s. Currencies: %s.</p>"
        % (
            len(result["transactions"]),
            len(result["flagged"]),
            _money(result["total_net"]),
            ", ".join(result["currencies"]) or "n/a",
        ),
        "<h2>Summary by category</h2><table>",
        "<tr><th>Category</th><th>Count</th><th>Gross</th><th>Fees</th><th>Net</th></tr>",
    ]
    for category in sorted(result["summary"]):
        bucket = result["summary"][category]
        parts.append(
            "<tr><td>%s</td><td>%d</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (
                esc(category),
                bucket["count"],
                _money(bucket["gross"]),
                _money(bucket["fee"]),
                _money(bucket["net"]),
            )
        )
    parts.append("</table>")
    if result["flagged"]:
        parts.append("<h2>Needs attention</h2><table>")
        parts.append("<tr><th>Date</th><th>Counterparty</th><th>Category</th><th>Flags</th></tr>")
        for txn in result["flagged"]:
            parts.append(
                "<tr><td>%s</td><td>%s</td><td>%s</td><td class='flag'>%s</td></tr>"
                % (esc(txn.date), esc(txn.name), esc(txn.category), esc("; ".join(txn.flags)))
            )
        parts.append("</table>")
    if ai_active and result["flagged"]:
        parts.append("<h2>Explanations</h2><table>")
        parts.append("<tr><th>Date</th><th>Counterparty</th><th>Flag</th>"
                     "<th>Explanation</th></tr>")
        for txn in result["flagged"]:
            for flag in txn.flags:
                parts.append(
                    "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                    % (
                        esc(txn.date), esc(txn.name), esc(flag),
                        esc(explain_flag(flag, txn, client=client,
                                         enabled=ai_active)),
                    )
                )
        parts.append("</table>")
    parts.append("<h2>All transactions</h2><table>")
    parts.append("<tr><th>Date</th><th>Counterparty</th><th>Type</th><th>Status</th>"
                 "<th>Gross</th><th>Fee</th><th>Net</th><th>ID</th></tr>")
    for txn in result["transactions"]:
        parts.append(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (
                esc(txn.date), esc(txn.name), esc(txn.type), esc(txn.status),
                _money(txn.gross), _money(abs(txn.fee)), _money(txn.net), esc(txn.txid),
            )
        )
    parts.append("</table></body></html>")
    return "\n".join(parts)
