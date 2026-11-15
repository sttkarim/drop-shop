"""Тесты слоя БД: товары, остатки, авто-списание, заказы."""

from __future__ import annotations

from app.db import Database


async def test_ensure_user_upsert(db: Database):
    u1 = await db.ensure_user(100, "a", "A")
    u2 = await db.ensure_user(100, "b", "B")
    assert u1["id"] == u2["id"]
    assert u2["username"] == "b"


async def test_add_product_and_sizes(db: Database):
    pid = await db.add_product("Кроссовки", "Бег", 5000, sizes=[("41", 3), ("42", 0)])
    sizes = await db.get_sizes(pid)
    assert [(r["size"], r["qty"]) for r in sizes] == [("41", 3), ("42", 0)]


async def test_adjust_stock(db: Database):
    pid = await db.add_product("Футболка", sizes=[("S", 5)])
    assert await db.adjust_stock(pid, "S", -2) is True
    assert await db.adjust_stock(pid, "S", -10) is False  # не хватает
    sizes = await db.get_sizes(pid)
    assert sizes[0]["qty"] == 3


async def test_create_order_decrements(db: Database):
    seller = await db.ensure_user(2001)
    pid = await db.add_product("Кроссовки", sizes=[("41", 3)])
    order_id = await db.create_order(seller["id"], pid, "41", 1, "СДЭК", "TK-1")
    assert order_id is not None
    sizes = await db.get_sizes(pid)
    assert sizes[0]["qty"] == 2  # списали автоматически


async def test_create_order_insufficient(db: Database):
    seller = await db.ensure_user(2001)
    pid = await db.add_product("Кроссовки", sizes=[("41", 1)])
    assert await db.create_order(seller["id"], pid, "41", 2, "СДЭК", "TK-1") is None
    sizes = await db.get_sizes(pid)
    assert sizes[0]["qty"] == 1  # ничего не списали


async def test_photos(db: Database):
    pid = await db.add_product("Кепка")
    await db.add_photo(pid, "/uploads/a.jpg", 0)
    await db.add_photo(pid, "/uploads/b.jpg", 1)
    photos = await db.get_photos(pid)
    assert [p["url"] for p in photos] == ["/uploads/a.jpg", "/uploads/b.jpg"]
