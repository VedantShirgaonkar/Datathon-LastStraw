from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Tuple


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _unb64url(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def sign_payload(payload: Dict[str, Any], secret: str, expires_at_epoch: int) -> str:
    envelope = {"payload": payload, "exp": int(expires_at_epoch)}
    raw = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    return _b64url(raw) + "." + _b64url(sig)


def verify_token(token: str, secret: str, now_epoch: int | None = None) -> Tuple[bool, Dict[str, Any] | None, str | None]:
    try:
        raw_b64, sig_b64 = token.split(".", 1)
        raw = _unb64url(raw_b64)
        sig = _unb64url(sig_b64)
    except Exception:
        return False, None, "invalid_format"

    expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return False, None, "bad_signature"

    try:
        envelope = json.loads(raw.decode("utf-8"))
    except Exception:
        return False, None, "bad_json"

    exp = int(envelope.get("exp") or 0)
    now = int(time.time() if now_epoch is None else now_epoch)
    if exp <= now:
        return False, None, "expired"

    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        return False, None, "bad_payload"

    return True, payload, None
