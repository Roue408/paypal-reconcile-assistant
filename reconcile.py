"""PayPal transaction reconciliation core (Python standard library only).

Fresh code written for the PayPal AI Hackathon entry.
Explanations are rule-based and labeled as such; an optional LLM explainer
is a clearly-marked TODO for the operator's own API key, off by default.
"""

import csv
import io
import re
from dataclasses import dataclass, field

ALIASES = {
    "date": ["date"],
    "time": ["time"],
    "name": ["name", "counterparty", "from email address", "to email address"],
    "type": ["type"],
    "status": ["status"],
    "currency": ["currency"],
    "gross": ["gross"],
    "fee": ["fee"],
    "net": ["net"],
    "txid": ["transaction id", "transaction id.", "id"],
}


def _norm(header):
    return re.sub(r"[^a-z0-9 ]", "", header.strip().lower())


def parse_amount(value):
    """Parse a money string. Returns 0.0 for blanks and unparseable input."""
    if value is None:
        return 0.0
    text = str(value).strip().replace("$", "").replace(",", "")
    if text in ("", "-"):
        return 0.0
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    try:
        amount = float(text)
    except ValueError:
        return 0.0
    return -amount if negative else amount


@dataclass
class Txn:
    date: str = ""
    name: str = ""
    type: str = ""
    status: str = ""
    currency: str = ""
    gross: float = 0.0
    fee: float = 0.0
    net: float = 0.0
    txid: str = ""
    category: str = "Other"
    flags: list = field(default_factory=list)


def categorize(txn):
    kind = txn.type.lower()
    if "refund" in kind:
        return "Refund"
    if "reversal" in kind:
        return "Reversal"
    if "subscription" in kind:
        return "Subscription"
    if "withdraw" in kind:
        return "Withdrawal"
    if "deposit" in kind or "bank credit" in kind:
        return "Deposit"
    if "hold" in kind:
        return "Hold"
    if "fee" in kind or "charge" in kind:
        return "Fee"
    if "payment" in kind or "transfer" in kind or "purchase" in kind:
        return "Payment received" if txn.gross >= 0 else "Payment sent"
    return "Other"


def parse_csv(text):
    """Parse a PayPal activity-export CSV (header names matched flexibly)."""
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return []
    mapping = {}
    for raw in reader.fieldnames:
        normalized = _norm(raw)
        for key, aliases in ALIASES.items():
            if normalized in aliases and key not in mapping:
                mapping[key] = raw
    txns = []
    for row in reader:
        def get(key, default=""):
            column = mapping.get(key)
            if column is None:
                return default
            return row.get(column, default) or default

        txn = Txn(
            date=get("date"),
            name=get("name"),
            type=get("type"),
            status=get("status"),
            currency=get("currency"),
            gross=parse_amount(get("gross")),
            fee=parse_amount(get("fee")),
            net=parse_amount(get("net")),
            txid=get("txid"),
        )
        txn.category = categorize(txn)
        txns.append(txn)
    return txns


def analyze(txns):
    """Flag discrepancies and summarize by category."""
    seen_ids = set()
    for txn in txns:
        fee_abs = abs(txn.fee)
        if abs((txn.gross - fee_abs) - txn.net) > 0.005:
            txn.flags.append("Net does not match Gross minus Fee")
        if txn.txid:
            if txn.txid in seen_ids:
                txn.flags.append("Duplicate transaction ID")
            else:
                seen_ids.add(txn.txid)
        if txn.status and txn.status.lower() not in ("completed", "cleared"):
            txn.flags.append("Status is %s - needs attention" % txn.status)
        if txn.gross and txn.category == "Payment received" and fee_abs > 0.10 * abs(txn.gross):
            txn.flags.append("Fee is over 10% of gross - check")
    summary = {}
    for txn in txns:
        bucket = summary.setdefault(
            txn.category, {"count": 0, "gross": 0.0, "fee": 0.0, "net": 0.0}
        )
        bucket["count"] += 1
        bucket["gross"] += txn.gross
        bucket["fee"] += abs(txn.fee)
        bucket["net"] += txn.net
    return {
        "transactions": txns,
        "summary": summary,
        "flagged": [t for t in txns if t.flags],
        "currencies": sorted({t.currency for t in txns if t.currency}),
        "total_net": sum(t.net for t in txns),
    }


def explain(txn):
    """One-line rule-based explanation for a transaction."""
    base = "%s: %s %s %.2f, fee %.2f, net %.2f." % (
        txn.category,
        txn.name or "unknown counterparty",
        txn.currency or "",
        txn.gross,
        abs(txn.fee),
        txn.net,
    )
    if txn.flags:
        base += " Attention: " + "; ".join(txn.flags) + "."
    return base
