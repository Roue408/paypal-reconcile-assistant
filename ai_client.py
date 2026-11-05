"""Optional Gemini client for AI explanations (Python standard library only).

This is the missing piece that made the AI explainer invisible in the
demo: explainer.py accepts an injected client, but app.py never built
one. This module builds one, and only one, and only when the operator
explicitly asks for it.

Rules, matching AGENTS.md:
- OFF by default. Nothing here runs unless the caller passes a client
  into build_report() or sets PAYPAL_LLM_EXPLAINER=1 AND provides a key.
- Key comes only from GEMINI_API_KEY or GOOGLE_API_KEY in the
  environment. It is never hardcoded, never logged, and never put in
  a report. The key is sent only to Google's Gemini API endpoint.
- Any API failure falls back to the rule-based explanation in
  explainer.py (that module catches client errors). No fake AI text
  is ever produced: if the API returns no text, explain_flag() falls
  back to rules.
- No new dependency: urllib only.
"""

import json
import os
import urllib.request

DEFAULT_MODEL = "gemini-2.5-flash"


def _key():
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""


class GeminiClient:
    """Minimal client with an explain(prompt) method for explainer.py."""

    def __init__(self, model=None, api_key=None, urlopen=None):
        self.model = model or os.environ.get("GEMINI_EXPLAIN_MODEL", DEFAULT_MODEL)
        self.api_key = api_key if api_key is not None else _key()
        self._urlopen = urlopen or urllib.request.urlopen
        if not self.api_key:
            raise RuntimeError(
                "Gemini API key not found. Set GEMINI_API_KEY in the "
                "environment (never in chat or in the repo)."
            )

    def explain(self, prompt):
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
            % self.model
        )
        body = json.dumps(
            {"contents": [{"parts": [{"text": prompt}]}]}
        ).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        with self._urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        for candidate in payload.get("candidates", []) or []:
            content = candidate.get("content", {}) or {}
            for part in content.get("parts", []) or []:
                text = part.get("text", "")
                if text:
                    return text
        raise RuntimeError("Gemini returned no text.")


def make_client():
    """Return a GeminiClient, or None when AI is not enabled / no key.

    Callers must check is_enabled() first; this helper just avoids
    raising for the common 'AI not requested' case.
    """
    from explainer import is_enabled

    if not is_enabled():
        return None
    try:
        return GeminiClient()
    except Exception:
        return None
