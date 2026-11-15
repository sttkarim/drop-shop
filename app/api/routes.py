"""REST API для Mini App (на Starlette, без pydantic)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from ..config import Config
from ..db import Database
from ..security import validate_init_data

TRANSPORT_COMPANIES = ["СДЭК", "Яндекс маркет", "Авито", "5post", "Почта России"]

ORDER_STATUSES = {"new", "confirmed", "shipped", "done"}


def _json(data, status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status)


def _err(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def _db(request: Request) -> Database:
    return request.app.state.db


def _cfg(request: Request) -> Config:
    return request.app.state.cfg


async def _auth(request: Request) -> tuple[dict, bool]:
    """Возвращает (user_row, is_admin). Если подпись неверна — (None, False)."""
    init = request.headers.get("x-init-data", "")
    data = validate_init_data(init, _cfg(request).bot_token)
    if not data or not data.get("user_id"):
        return None, False
    db = _db(request)
    cfg = _cfg(request)
    user = await db.ensure_user(data["user_id"], data["username"], data["first_name"])
    is_admin = (data["user_id"] in cfg.admin_ids) or (user["role"] == "admin")
    if data["user_id"] in cfg.admin_ids and user["role"] != "admin":
        await db.set_role(data["user_id"], "admin")
        user = await db.get_user(data["user_id"])
    return user, is_admin


def _product_dict(p: dict) -> dict:
    return {
        "id": p["id"],
        "name": p["name"],
        "description": p["description"],
        "price": p["price"],
        "main_photo": p["main_photo"],
        "total_qty": p["total_qty"],
        "sizes_count": p["sizes_count"],
    }


# ---------------- эндпоинты ----------------

async def me(request: Request):
    user, is_admin = await _auth(request)
    if user is None:
        return _err("Неверная подпись initData", 401)
    return _json(
        {"user_id": user["telegram_id"], "username": user["username"], "is_admin": is_admin}
    )


async def catalog(request: Request):
    user, _ = await _auth(request)
    if user is None:
        return _err("Неверная подпись initData", 401)
    db = _db(request)
    cfg = _cfg(request)
    rows = await db.list_products(limit=cfg.items_per_page)
    return _json({"items": [_product_dict(r) for r in rows]})


async def product(request: Request):
    user, _ = await _auth(request)
    if user is None:
        return _err("Неверная подпись initData", 401)
    db = _db(request)
    pid = int(request.path_params["product_id"])
    p = await db.get_product(pid)
    if p is None:
        return _err("Товар не найден", 404)
    sizes = [{"size": r["size"], "qty": r["qty"]} for r in await db.get_sizes(pid)]
    photos = [r["url"] for r in await db.get_photos(pid)]
    return _json(
        {
            "id": p["id"],
            "name": p["name"],
            "description": p["description"],
            "price": p["price"],
            "main_photo": p["main_photo"],
            "photos": photos,
            "sizes": sizes,
            "transport_companies": TRANSPORT_COMPANIES,
        }
    )


async def create_order(request: Request):
    user, _ = await _auth(request)
    if user is None:
        return _err("Неверная подпись initData", 401)
    db = _db(request)
    try:
        body = await request.json()
    except Exception:
        return _err("Некорректный JSON")

    product_id = int(body.get("product_id", 0))
    size = str(body.get("size", "")).strip()
    qty = int(body.get("qty", 1) or 1)
    transport = str(body.get("transport_company", "")).strip()
    track = str(body.get("track_number", "")).strip()

    p = await db.get_product(product_id)
    if p is None:
        return _err("Товар не найден", 404)
    if not size or qty < 1:
        return _err("Укажите размер и количество")
    if not transport:
        return _err("Укажите транспортную компанию")
    if not track:
        return _err("Укажите трек-номер")

    order_id = await db.create_order(user["id"], product_id, size, qty, transport, track)
    if order_id is None:
        return _err("Недостаточно остатка по этому размеру", 409)
    return _json({"ok": True, "order_id": order_id}, 201)


async def my_orders(request: Request):
    user, _ = await _auth(request)
    if user is None:
        return _err("Неверная подпись initData", 401)
    db = _db(request)
    rows = await db.list_orders_by_seller(user["id"])
    return _json({"items": [dict(r) for r in rows]})


async def admin_orders(request: Request):
    _, is_admin = await _auth(request)
    if not is_admin:
        return _err("Доступ только для администратора", 403)
    db = _db(request)
    rows = await db.list_all_orders()
    return _json({"items": [dict(r) for r in rows]})


async def admin_set_stock(request: Request):
    _, is_admin = await _auth(request)
    if not is_admin:
        return _err("Доступ только для администратора", 403)
    db = _db(request)
    try:
        body = await request.json()
    except Exception:
        return _err("Некорректный JSON")
    product_id = int(body.get("product_id", 0))
    size = str(body.get("size", "")).strip()
    qty = int(body.get("qty", 0))
    if not size or qty < 0:
        return _err("Укажите размер и количество (≥ 0)")
    await db.set_size(product_id, size, qty)
    return _json({"ok": True})


async def admin_order_status(request: Request):
    _, is_admin = await _auth(request)
    if not is_admin:
        return _err("Доступ только для администратора", 403)
    db = _db(request)
    order_id = int(request.path_params["order_id"])
    try:
        body = await request.json()
    except Exception:
        return _err("Некорректный JSON")
    status = str(body.get("status", "")).strip()
    if status not in ORDER_STATUSES:
        return _err("Неверный статус")
    await db.update_order_status(order_id, status)
    return _json({"ok": True})


def _parse_sizes(raw: str | None) -> list[tuple[str, int]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    result: list[tuple[str, int]] = []
    for item in data:
        if isinstance(item, str):
            result.append((item, 0))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            result.append((str(item[0]), int(item[1])))
    return result


async def _save_upload(upload, uploads_dir: str) -> str:
    content = await upload.read()
    filename = (upload.filename or "").lower()
    ext = Path(filename).suffix if Path(filename).suffix else ".jpg"
    name = f"{uuid.uuid4().hex}{ext}"
    path = Path(uploads_dir) / name
    path.write_bytes(content)
    return f"/uploads/{name}"


async def admin_add_product(request: Request):
    _, is_admin = await _auth(request)
    if not is_admin:
        return _err("Доступ только для администратора", 403)
    db = _db(request)
    cfg = _cfg(request)
    try:
        form = await request.form()
    except Exception:
        return _err("Ожидается multipart-форма")

    name = str(form.get("name", "")).strip()
    if not name:
        return _err("Укажите название товара")
    description = str(form.get("description", ""))
    price = int(form.get("price", 0) or 0)
    sizes = _parse_sizes(form.get("sizes"))

    Path(cfg.uploads_dir).mkdir(parents=True, exist_ok=True)
    main_photo = ""
    main = form.get("main")
    if main is not None and getattr(main, "filename", None):
        main_photo = await _save_upload(main, cfg.uploads_dir)

    pid = await db.add_product(name, description, price, main_photo, sizes)

    photos = form.getlist("photos")
    for i, photo in enumerate(photos):
        if getattr(photo, "filename", None):
            url = await _save_upload(photo, cfg.uploads_dir)
            await db.add_photo(pid, url, i)

    return _json({"ok": True, "product_id": pid}, 201)


routes = [
    Route("/api/me", me, methods=["GET"]),
    Route("/api/catalog", catalog, methods=["GET"]),
    Route("/api/product/{product_id:int}", product, methods=["GET"]),
    Route("/api/orders", create_order, methods=["POST"]),
    Route("/api/orders/mine", my_orders, methods=["GET"]),
    Route("/api/admin/orders", admin_orders, methods=["GET"]),
    Route("/api/admin/stock", admin_set_stock, methods=["PATCH"]),
    Route("/api/admin/orders/{order_id:int}/status", admin_order_status, methods=["PATCH"]),
    Route("/api/admin/products", admin_add_product, methods=["POST"]),
]
