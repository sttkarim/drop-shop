"""Конфигурация приложения: переменные окружения и .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # dropapp/
load_dotenv(BASE_DIR / ".env")


def _parse_admin_ids(raw: str | None) -> set[int]:
    result: set[int] = set()
    if not raw:
        return result
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            result.add(int(part))
    return result


@dataclass
class Config:
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", "").strip())
    admin_ids: set[int] = field(
        default_factory=lambda: _parse_admin_ids(os.getenv("ADMIN_IDS"))
    )
    db_path: str = field(
        default_factory=lambda: os.getenv("DB_PATH") or str(BASE_DIR / "data" / "shop.db")
    )
    # Публичный HTTPS-адрес Mini App (для кнопки web_app в боте). Локально — туннель.
    webapp_url: str = field(default_factory=lambda: os.getenv("WEBAPP_URL", "").strip())
    uploads_dir: str = field(
        default_factory=lambda: os.getenv("UPLOADS_DIR") or str(BASE_DIR / "static" / "uploads")
    )
    items_per_page: int = field(
        default_factory=lambda: int(os.getenv("ITEMS_PER_PAGE", "24") or 24)
    )
    proxy_url: str = field(default_factory=lambda: os.getenv("PROXY_URL", "").strip())
    start_bot: bool = field(
        default_factory=lambda: os.getenv("START_BOT", "1").strip().lower() not in ("0", "false", "no")
    )

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token)


def load_config() -> Config:
    return Config()
