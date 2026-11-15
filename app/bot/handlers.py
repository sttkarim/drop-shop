"""Telegram-бот: команды и кнопка открытия Mini App."""

from __future__ import annotations

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from ..config import Config


def build_bot_application(cfg: Config) -> Application:
    builder = ApplicationBuilder().token(cfg.bot_token)
    if cfg.proxy_url:
        builder = builder.proxy_url(cfg.proxy_url)
    app = builder.build()
    app.bot_data["cfg"] = cfg

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("catalog", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("help", cmd_help))

    return app


def _menu_markup(cfg: Config, is_admin: bool) -> ReplyKeyboardMarkup | None:
    buttons = []
    if cfg.webapp_url:
        buttons.append([KeyboardButton(text="🛍 Каталог", web_app=WebAppInfo(url=cfg.webapp_url))])
        if is_admin:
            buttons.append(
                [KeyboardButton(text="⚙️ Админ-панель", web_app=WebAppInfo(url=cfg.webapp_url))]
            )
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True) if buttons else None


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: Config = context.bot_data["cfg"]
    user = update.effective_user
    is_admin = user.id in cfg.admin_ids
    name = user.first_name or "друг"
    if cfg.webapp_url:
        text = (
            f"👋 Здравствуйте, {name}!\n\n"
            "Это магазин STT Drop. Нажмите кнопку ниже, чтобы открыть каталог "
            "с фото и актуальным наличием по размерам."
        )
    else:
        text = "👋 Бот работает, но адрес Mini App не настроен (WEBAPP_URL в .env)."
    await update.effective_message.reply_text(text, reply_markup=_menu_markup(cfg, is_admin))


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: Config = context.bot_data["cfg"]
    user = update.effective_user
    if user.id not in cfg.admin_ids:
        await update.effective_message.reply_text("⛔️ Доступ только для администратора.")
        return
    if not cfg.webapp_url:
        await update.effective_message.reply_text("Адрес Mini App не настроен (WEBAPP_URL).")
        return
    await update.effective_message.reply_text(
        "⚙️ <b>Админ-панель</b>\n\nЗдесь вы добавляете товары с фото и меняете остатки.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(text="⚙️ Открыть админ-панель", web_app=WebAppInfo(url=cfg.webapp_url))]],
            resize_keyboard=True,
        ),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "🛍 <b>Каталог</b> — товары, фото и остатки по размерам.\n"
        "📦 <b>Заказ</b> — выберите размер, транспортную компанию и впишите трек-номер.\n"
        "Заказы и остатки обновляются автоматически.",
        parse_mode="HTML",
    )
