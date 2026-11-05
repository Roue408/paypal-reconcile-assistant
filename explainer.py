"""Optional AI-assisted explanations for reconciliation flags (stdlib only).

Rule-based explanations are always available and are the default. An AI
refinement path exists but is OFF unless the operator both enables it with an
environment variable and injects a client. This module never constructs a
client, never reads a key, and never makes a network call itself.
"""

import os

# Operator-facing switch. Absent, empty, or false-like means rules only.
ENABLE_ENV = "PAYPAL_LLM_EXPLAINER"
_TRUTHY = ("1", "true", "yes", "on")

# Every AI-refined explanation carries this marker so reports can label it.
AI_LABEL = "AI-generated"


def is_enabled(environ=None):
    """Return True only when the operator explicitly enabled the LLM path."""
    env = os.environ if environ is None else environ
    return str(env.get(ENABLE_ENV, "")).strip().lower() in _TRUTHY


def _money(value):
    try:
        return "%.2f" % float(value)
    except (TypeError, ValueError):
        return "0.00"


def rule_explanation(flag, transaction):
    """Plain-English, rule-based one-sentence explanation for a flag."""
    flag = str(flag or "").strip()
    name = transaction.name or "this counterparty"
    if flag.startswith("Net does not match"):
        return (
            "%s shows a net of %s, which does not equal gross %s minus the "
            "%s fee, so a fee, refund, or adjustment may be missing or counted "
            "twice." % (
                name, _money(transaction.net), _money(transaction.gross),
                _money(abs(transaction.fee)),
            )
        )
    if flag.startswith("Duplicate transaction ID"):
        return (
            "Transaction ID %s appears more than once, so one of these rows may "
            "be a duplicate that should be removed." % (transaction.txid or "(blank)")
        )
    if flag.startswith("Status is"):
        status = transaction.status or "unknown"
        return (
            "The status of %s is '%s' rather than Completed, so the money may "
            "still settle, reverse, or need follow-up." % (name, status)
        )
    if flag.startswith("Fee is over 10%"):
        return (
            "The fee of %s is more than 10%% of the gross %s from %s, which is "
            "unusually high for this payment and should be checked." % (
                _money(abs(transaction.fee)), _money(transaction.gross), name,
            )
        )
    return (
        "%s was flagged as '%s' and should be reviewed before trusting the "
        "totals." % (name, flag or "a discrepancy")
    )


def _call_client(client, prompt):
    """Invoke an injected client: a callable, or an object with .explain()."""
    if client is None:
        return None
    if callable(client):
        return client(prompt)
    explain = getattr(client, "explain", None)
    if callable(explain):
        return explain(prompt)
    raise TypeError("LLM client must be callable or expose an explain() method")


def _prompt(flag, transaction):
    return (
        "Explain this PayPal reconciliation discrepancy in one plain-English "
        "sentence for a small-business owner. Do not give advice beyond what "
        "the data shows.\n"
        "Flag: %s\n"
        "Counterparty: %s\nCategory: %s\nStatus: %s\nCurrency: %s\n"
        "Gross: %s\nFee: %s\nNet: %s\nTransaction ID: %s\n" % (
            flag,
            transaction.name or "unknown",
            transaction.category,
            transaction.status or "unknown",
            transaction.currency or "n/a",
            _money(transaction.gross),
            _money(abs(transaction.fee)),
            _money(transaction.net),
            transaction.txid or "(blank)",
        )
    )


def explain_flag(flag, transaction, client=None, enabled=None):
    """Explain one flag in one sentence.

    Starts from the rule-based explanation. Refines it through the injected
    client only when the path is enabled (explicitly or via the env var) and a
    client is present; otherwise returns the rule-based text unchanged.
    Refined text is prefixed with the AI-generated label.
    """
    base = rule_explanation(flag, transaction)
    active = is_enabled() if enabled is None else bool(enabled)
    if not active or client is None:
        return base
    try:
        refined = _call_client(client, _prompt(flag, transaction))
    except Exception:
        # A failing or unavailable client must never break a report.
        return base
    if not isinstance(refined, str):
        refined = str(refined) if refined is not None else ""
    refined = " ".join(refined.split())
    if not refined:
        return base
    return "%s: %s" % (AI_LABEL, refined)
