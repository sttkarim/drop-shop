"""Точка входа: Starlette-приложение (Mini App + REST API) и Telegram-бот в одном процессе.

Запуск:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import logging
import socket
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from .api.routes import routes
from .bot.handlers import build_bot_application
from .config import BASE_DIR, Config, load_config
from .db import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("dropapp")


def force_ipv4() -> None:
    """На машинах без IPv6 httpx зависает на таймауте — принудительно используем IPv4."""
    original = socket.getaddrinfo

    def getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
        results = original(host, port, family, type, proto, flags)
        if family in (0, socket.AF_UNSPEC):
            results = [r for r in results if r[0] == socket.AF_INET]
        return results

    socket.getaddrinfo = getaddrinfo_ipv4


async def _run_bot(cfg: Config) -> None:
    """Бесконечно держит бота живым: при недоступности Telegram пересоздаёт приложение."""
    while True:
        bot_app = build_bot_application(cfg)
        try:
            await bot_app.initialize()
            await bot_app.start()
            logger.info("Telegram-бот запущен")
            await bot_app.updater.start_polling(drop_pending_updates=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # сеть до Telegram может мигать
            logger.warning("Бот недоступен (%s). Повтор через 10 с…", type(exc).__name__)
            await asyncio.sleep(10)
        finally:
            try:
                await bot_app.shutdown()
            except Exception:
                pass


@asynccontextmanager
async def lifespan(app: Starlette):
    cfg: Config = app.state.cfg
    db = Database(cfg.db_path)
    await db.connect()
    app.state.db = db

    bot_task = None
    if cfg.start_bot:
        bot_task = asyncio.create_task(_run_bot(cfg))
    logger.info("Mini App запущен (каталог и API доступны)")
    try:
        yield
    finally:
        if bot_task is not None:
            bot_task.cancel()
            try:
                await bot_task
            except (asyncio.CancelledError, Exception):
                pass
        await db.close()


def create_app(cfg: Config | None = None) -> Starlette:
    force_ipv4()
    if cfg is None:
        cfg = load_config()
    Path(cfg.uploads_dir).mkdir(parents=True, exist_ok=True)

    app = Starlette(
        routes=[
            *routes,
            Mount("/uploads", StaticFiles(directory=cfg.uploads_dir)),
            Mount("/", StaticFiles(directory=str(BASE_DIR / "static"), html=True)),
        ],
        lifespan=lifespan,
    )
    app.state.cfg = cfg
    return app


app = create_app()
