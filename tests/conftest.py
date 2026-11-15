"""Общие фикстуры для тестов dropapp."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
import pytest_asyncio

from app.config import Config
from app.db import Database

TOKEN = "123:TEST"
ADMIN_ID = 1001
SELLER_ID = 2001


@pytest_asyncio.fixture
async def db(tmp_path):
    d = Database(str(tmp_path / "test.db"))
    await d.connect()
    yield d
    await d.close()


def make_config(tmp_path: Path) -> Config:
    return Config(
        bot_token=TOKEN,
        admin_ids={ADMIN_ID},
        db_path=str(tmp_path / "api.db"),
        uploads_dir=str(tmp_path / "uploads"),
        start_bot=False,
    )
