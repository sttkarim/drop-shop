"""Тесты проверки подписи initData."""

from __future__ import annotations

from app.security import validate_init_data
from tests.helpers import make_init_data

TOKEN = "123:TEST"


def test_valid_signature():
    init = make_init_data(TOKEN, user_id=2001, username="seller")
    data = validate_init_data(init, TOKEN)
    assert data is not None
    assert data["user_id"] == 2001
    assert data["username"] == "seller"


def test_wrong_token_rejected():
    init = make_init_data("other:token", user_id=2001)
    assert validate_init_data(init, TOKEN) is None


def test_tampered_data_rejected():
    init = make_init_data(TOKEN, user_id=2001)
    tampered = init.replace("2001", "9999")  # меняем подписанное поле user id
    assert validate_init_data(tampered, TOKEN) is None


def test_empty_rejected():
    assert validate_init_data("", TOKEN) is None
    assert validate_init_data("hash=abc", TOKEN) is None
