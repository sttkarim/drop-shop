"""Вспомогательные функции для тестов."""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.parse


def make_init_data(token: str, user_id: int = 2001, username: str = "seller") -> str:
    """Формирует корректно подписанный initData (как это делает Telegram)."""
    user = json.dumps({"id": user_id, "first_name": "Test", "username": username})
    params = {"auth_date": "1700000000", "query_id": "AAABBBCCC", "user": user}
    check = "\n".join(f"{k}={params[k]}" for k in sorted(params))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(params)
