"""Проверка подписи initData от Telegram Mini App."""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.parse


def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """Проверяет подпись initData. Возвращает словарь полей или None при неверной подписи.

    Telegram подписывает данные так:
      secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
      hash       = HMAC_SHA256(key=secret_key, msg=data_check_string)
    где data_check_string = отсортированные пары "key=value" через \\n (без поля hash).
    """
    if not init_data or not bot_token:
        return None
    params = dict(urllib.parse.parse_qsl(init_data))
    received_hash = params.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={params[k]}" for k in sorted(params))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated, received_hash):
        return None

    user_raw = params.get("user") or "{}"
    try:
        user = json.loads(user_raw)
    except (ValueError, TypeError):
        user = {}

    return {
        "user_id": user.get("id"),
        "username": user.get("username", ""),
        "first_name": user.get("first_name", ""),
        "auth_date": params.get("auth_date"),
        "params": params,
    }
