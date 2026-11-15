"""Слой работы с базой данных (SQLite через aiosqlite)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import aiosqlite

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username    TEXT NOT NULL DEFAULT '',
    first_name  TEXT NOT NULL DEFAULT '',
    role        TEXT NOT NULL DEFAULT 'seller',
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price       INTEGER NOT NULL DEFAULT 0,
    main_photo  TEXT NOT NULL DEFAULT '',
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS product_photos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    url        TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS product_sizes (
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    size       TEXT NOT NULL,
    qty        INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (product_id, size)
);

CREATE TABLE IF NOT EXISTS orders (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id         INTEGER NOT NULL REFERENCES users(id),
    product_id        INTEGER NOT NULL REFERENCES products(id),
    size              TEXT NOT NULL,
    qty               INTEGER NOT NULL DEFAULT 1,
    transport_company TEXT NOT NULL,
    track_number      TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'new',
    created_at        TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""


class Database:
    def __init__(self, path: str) -> None:
        self.path = str(path)
        self.db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = await aiosqlite.connect(self.path)
        self.db.row_factory = aiosqlite.Row
        await self.db.executescript(SCHEMA)
        await self.db.commit()

    async def close(self) -> None:
        if self.db is not None:
            await self.db.close()
            self.db = None

    # ---------- пользователи ----------

    async def ensure_user(self, telegram_id: int, username: str = "", first_name: str = "") -> aiosqlite.Row:
        await self.db.execute(
            "INSERT INTO users (telegram_id, username, first_name) VALUES (?, ?, ?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name",
            (telegram_id, username, first_name),
        )
        await self.db.commit()
        cur = await self.db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        return await cur.fetchone()

    async def get_user(self, telegram_id: int) -> aiosqlite.Row | None:
        cur = await self.db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        return await cur.fetchone()

    async def is_admin(self, telegram_id: int) -> bool:
        user = await self.get_user(telegram_id)
        return bool(user and user["role"] == "admin")

    async def set_role(self, telegram_id: int, role: str) -> None:
        await self.db.execute("UPDATE users SET role = ? WHERE telegram_id = ?", (role, telegram_id))
        await self.db.commit()

    # ---------- товары ----------

    async def add_product(
        self,
        name: str,
        description: str = "",
        price: int = 0,
        main_photo: str = "",
        sizes: Iterable[str | tuple[str, int]] | None = None,
    ) -> int:
        cur = await self.db.execute(
            "INSERT INTO products (name, description, price, main_photo) VALUES (?, ?, ?, ?)",
            (name.strip(), description, int(price), main_photo),
        )
        pid = cur.lastrowid
        if sizes:
            for item in sizes:
                size, qty = (item, 0) if isinstance(item, str) else (item[0], int(item[1]))
                await self._set_size(pid, size, qty, append=True)
        await self.db.commit()
        return pid

    async def get_product(self, pid: int) -> aiosqlite.Row | None:
        cur = await self.db.execute("SELECT * FROM products WHERE id = ?", (pid,))
        return await cur.fetchone()

    async def update_product(
        self, pid: int, name=None, description=None, price=None, main_photo=None
    ) -> None:
        fields, values = [], []
        for col, val in (
            ("name", name), ("description", description), ("price", price), ("main_photo", main_photo)
        ):
            if val is not None:
                fields.append(f"{col} = ?")
                values.append(val)
        if fields:
            fields.append("updated_at = datetime('now','localtime')")
            values.append(pid)
            await self.db.execute(f"UPDATE products SET {', '.join(fields)} WHERE id = ?", values)
            await self.db.commit()

    async def set_active(self, pid: int, active: bool) -> None:
        await self.db.execute("UPDATE products SET is_active = ? WHERE id = ?", (1 if active else 0, pid))
        await self.db.commit()

    async def delete_product(self, pid: int) -> None:
        await self.db.execute("DELETE FROM products WHERE id = ?", (pid,))
        await self.db.commit()

    async def count_products(self) -> int:
        cur = await self.db.execute("SELECT COUNT(*) AS c FROM products WHERE is_active = 1")
        return int((await cur.fetchone())["c"])

    async def list_products(self, offset: int = 0, limit: int | None = None) -> list[aiosqlite.Row]:
        sql = (
            "SELECT p.id, p.name, p.description, p.price, p.main_photo, "
            "COALESCE(SUM(s.qty), 0) AS total_qty, COUNT(s.size) AS sizes_count "
            "FROM products p LEFT JOIN product_sizes s ON s.product_id = p.id "
            "WHERE p.is_active = 1 GROUP BY p.id ORDER BY p.name"
        )
        args: tuple = ()
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            args = (limit, offset)
        cur = await self.db.execute(sql, args)
        return list(await cur.fetchall())

    async def get_sizes(self, pid: int) -> list[aiosqlite.Row]:
        cur = await self.db.execute(
            "SELECT size, qty, sort_order FROM product_sizes "
            "WHERE product_id = ? ORDER BY sort_order, size", (pid,),
        )
        return list(await cur.fetchall())

    async def _set_size(self, pid: int, size: str, qty: int, append: bool = False) -> None:
        size = size.strip()
        row = await (await self.db.execute(
            "SELECT sort_order FROM product_sizes WHERE product_id = ? AND size = ?", (pid, size)
        )).fetchone()
        if row is not None:
            await self.db.execute(
                "UPDATE product_sizes SET qty = ? WHERE product_id = ? AND size = ?",
                (int(qty), pid, size),
            )
            return
        if append:
            m = await (await self.db.execute(
                "SELECT COALESCE(MAX(sort_order), -1) AS m FROM product_sizes WHERE product_id = ?", (pid,)
            )).fetchone()
            sort_order = int(m["m"]) + 1
        else:
            sort_order = 0
        await self.db.execute(
            "INSERT INTO product_sizes (product_id, size, qty, sort_order) VALUES (?, ?, ?, ?)",
            (pid, size, int(qty), sort_order),
        )

    async def set_size(self, pid: int, size: str, qty: int, append: bool = False) -> None:
        await self._set_size(pid, size, int(qty), append=append)
        await self.db.commit()

    async def adjust_stock(self, pid: int, size: str, delta: int) -> bool:
        """Атомарно списывает/добавляет остаток. Возвращает False, если остатка не хватает."""
        cur = await self.db.execute(
            "UPDATE product_sizes SET qty = qty + ? WHERE product_id = ? AND size = ? AND qty + ? >= 0",
            (int(delta), pid, size, int(delta)),
        )
        await self.db.commit()
        return cur.rowcount > 0

    # ---------- фото ----------

    async def add_photo(self, pid: int, url: str, sort_order: int) -> None:
        await self.db.execute(
            "INSERT INTO product_photos (product_id, url, sort_order) VALUES (?, ?, ?)",
            (pid, url, sort_order),
        )
        await self.db.commit()

    async def get_photos(self, pid: int) -> list[aiosqlite.Row]:
        cur = await self.db.execute(
            "SELECT id, url, sort_order FROM product_photos WHERE product_id = ? ORDER BY sort_order, id",
            (pid,),
        )
        return list(await cur.fetchall())

    async def clear_photos(self, pid: int) -> None:
        await self.db.execute("DELETE FROM product_photos WHERE product_id = ?", (pid,))
        await self.db.commit()

    # ---------- заказы ----------

    async def create_order(
        self, seller_id: int, product_id: int, size: str, qty: int, transport: str, track: str
    ) -> int | None:
        """Создаёт заказ и списывает остаток. Возвращает id заказа или None, если не хватает."""
        ok = await self.adjust_stock(product_id, size, -qty)
        if not ok:
            return None
        cur = await self.db.execute(
            "INSERT INTO orders (seller_id, product_id, size, qty, transport_company, track_number) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (seller_id, product_id, size, int(qty), transport, track),
        )
        await self.db.commit()
        return cur.lastrowid

    async def list_orders_by_seller(self, seller_id: int) -> list[aiosqlite.Row]:
        cur = await self.db.execute(
            "SELECT o.*, p.name AS product_name, p.main_photo FROM orders o "
            "JOIN products p ON p.id = o.product_id "
            "WHERE o.seller_id = ? ORDER BY o.id DESC", (seller_id,),
        )
        return list(await cur.fetchall())

    async def list_all_orders(self) -> list[aiosqlite.Row]:
        cur = await self.db.execute(
            "SELECT o.*, p.name AS product_name, u.username AS seller_username, u.first_name AS seller_name "
            "FROM orders o JOIN products p ON p.id = o.product_id JOIN users u ON u.id = o.seller_id "
            "ORDER BY o.id DESC"
        )
        return list(await cur.fetchall())

    async def get_order(self, order_id: int) -> aiosqlite.Row | None:
        cur = await self.db.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        return await cur.fetchone()

    async def update_order_status(self, order_id: int, status: str) -> None:
        await self.db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        await self.db.commit()
