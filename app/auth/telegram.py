"""Telegram WebApp initData validation (server-side, per Telegram spec)."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class TelegramAuth:
    def __init__(self, bot_token: str, max_age_seconds: int = 86400):
        self.bot_token = bot_token
        self.max_age = max_age_seconds

    def validate(self, init_data: str) -> dict | None:
        """Validate initData signature. Returns parsed data or None."""
        if not init_data or not self.bot_token:
            return None
        try:
            pairs = dict(parse_qsl(init_data, keep_blank_values=True))
            received_hash = pairs.pop("hash", "")
            if not received_hash:
                return None
            data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
            secret = hmac.new(b"WebAppData", self.bot_token.encode(), hashlib.sha256).digest()
            calc = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(calc, received_hash):
                return None
            auth_date = int(pairs.get("auth_date", "0") or 0)
            if auth_date and (time.time() - auth_date) > self.max_age:
                return None  # replay protection: stale auth
            out = dict(pairs)
            if "user" in out:
                try:
                    out["user"] = json.loads(out["user"])
                except Exception:
                    return None
            return out
        except Exception:
            return None
