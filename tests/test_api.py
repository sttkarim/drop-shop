"""Тесты REST API через TestClient (без запуска бота)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from starlette.testclient import TestClient

from app.db import Database
from app.main import create_app
from tests.conftest import ADMIN_ID, SELLER_ID, TOKEN, make_config
from tests.helpers import make_init_data


def _seed(cfg, seller_id=SELLER_ID):
    async def run():
        d = Database(cfg.db_path)
        await d.connect()
        await d.ensure_user(seller_id, "seller", "Seller")
        pid = await d.add_product("Кроссовки", "Беговые", 5000, sizes=[("41", 3), ("42", 0)])
        await d.close()
        return pid

    return asyncio.run(run())


def _headers(user_id=SELLER_ID):
    return {"X-Init-Data": make_init_data(TOKEN, user_id)}


def test_catalog_empty(tmp_path: Path):
    cfg = make_config(tmp_path)
    with TestClient(create_app(cfg)) as client:
        r = client.get("/api/catalog", headers=_headers())
        assert r.status_code == 200
        assert r.json()["items"] == []


def test_catalog_and_product(tmp_path: Path):
    cfg = make_config(tmp_path)
    pid = _seed(cfg)
    with TestClient(create_app(cfg)) as client:
        r = client.get("/api/catalog", headers=_headers())
        assert len(r.json()["items"]) == 1
        assert r.json()["items"][0]["total_qty"] == 3

        r = client.get(f"/api/product/{pid}", headers=_headers())
        body = r.json()
        assert body["name"] == "Кроссовки"
        assert body["sizes"] == [{"size": "41", "qty": 3}, {"size": "42", "qty": 0}]
        assert body["transport_companies"] == ["СДЭК", "Яндекс маркет", "Авито", "5post", "Почта России"]


def test_order_auto_decrements_stock(tmp_path: Path):
    cfg = make_config(tmp_path)
    pid = _seed(cfg)
    with TestClient(create_app(cfg)) as client:
        r = client.post("/api/orders", headers=_headers(), json={
            "product_id": pid, "size": "41", "qty": 1,
            "transport_company": "СДЭК", "track_number": "TK-123",
        })
        assert r.status_code == 201

        # остаток списался автоматически
        r = client.get(f"/api/product/{pid}", headers=_headers())
        sizes = r.json()["sizes"]
        assert sizes[0]["qty"] == 2


def test_order_insufficient_stock(tmp_path: Path):
    cfg = make_config(tmp_path)
    pid = _seed(cfg)
    with TestClient(create_app(cfg)) as client:
        r = client.post("/api/orders", headers=_headers(), json={
            "product_id": pid, "size": "41", "qty": 99,
            "transport_company": "СДЭК", "track_number": "TK-123",
        })
        assert r.status_code == 409


def test_order_requires_track_and_transport(tmp_path: Path):
    cfg = make_config(tmp_path)
    pid = _seed(cfg)
    with TestClient(create_app(cfg)) as client:
        r = client.post("/api/orders", headers=_headers(), json={
            "product_id": pid, "size": "41", "qty": 1,
            "transport_company": "", "track_number": "",
        })
        assert r.status_code == 400


def test_admin_stock_requires_admin(tmp_path: Path):
    cfg = make_config(tmp_path)
    pid = _seed(cfg)
    with TestClient(create_app(cfg)) as client:
        # продавец не может менять остатки
        r = client.patch("/api/admin/stock", headers=_headers(SELLER_ID), json={
            "product_id": pid, "size": "41", "qty": 10,
        })
        assert r.status_code == 403

        # админ может
        r = client.patch("/api/admin/stock", headers=_headers(ADMIN_ID), json={
            "product_id": pid, "size": "41", "qty": 10,
        })
        assert r.status_code == 200
        r = client.get(f"/api/product/{pid}", headers=_headers())
        assert r.json()["sizes"][0]["qty"] == 10


def test_unauthorized_rejected(tmp_path: Path):
    cfg = make_config(tmp_path)
    with TestClient(create_app(cfg)) as client:
        r = client.get("/api/catalog", headers={"X-Init-Data": "hash=bad"})
        assert r.status_code == 401
