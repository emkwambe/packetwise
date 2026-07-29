"""Signed session tokens for the dashboard.

The dashboard used to ship the API key in its own HTML, which put a working
credential in front of anyone who loaded the page (ISSUE-001). It now logs in
with a password and receives an HttpOnly cookie instead, so no credential is
readable from page source.

Tokens are stateless and HMAC-signed: the payload is an expiry timestamp and
the signature proves the server issued it. There is no session store to
invalidate, which is the trade-off documented in ADR-004 — logging out clears
the cookie on the client, but an already-issued token stays valid until it
expires.

This is a single shared password, not per-user identity. It gates access; it
does not attribute actions to a person.
"""
import hashlib
import hmac
import time
from typing import Optional

SESSION_COOKIE = "pw_session"

# Defaults that must never reach production. `main.py` warns at startup if
# either is still in place while DEBUG is off.
INSECURE_DEFAULTS = {
    "dev-key-change-in-production",
    "dev-password-change-in-production",
    "dev-secret-change-in-production",
}


def create_session_token(secret: str, ttl_hours: int = 12) -> str:
    """Issue a signed token of the form '<expiry_epoch>.<hex_signature>'."""
    expiry = int(time.time()) + int(ttl_hours * 3600)
    payload = str(expiry)
    signature = _sign(payload, secret)
    return f"{payload}.{signature}"


def verify_session_token(token: Optional[str], secret: str) -> bool:
    """True only if the signature is ours and the token has not expired."""
    if not token:
        return False
    payload, _, signature = token.partition(".")
    if not payload or not signature:
        return False
    if not hmac.compare_digest(signature, _sign(payload, secret)):
        return False
    try:
        return int(payload) > time.time()
    except ValueError:
        return False


def check_password(supplied: Optional[str], expected: str) -> bool:
    """Constant-time password comparison."""
    if not supplied:
        return False
    return hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))


def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"),
                    hashlib.sha256).hexdigest()
