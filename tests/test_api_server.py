"""REST API テスト"""

import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from src.api.server import APIServer
from src.database.models import Database
from src.database.repository import NotificationRepository


def _make_fixtures():
    """同期でDB・repo・mock_bot・api_serverを作る。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db = Database(db_path=tmp.name)
    db.initialize()
    repo = NotificationRepository(db)

    bot = MagicMock()
    bot.default_channel_id = 123456789
    mock_channel = AsyncMock()
    mock_channel.send = AsyncMock()
    bot.get_channel = MagicMock(return_value=mock_channel)

    api_server = APIServer(repo=repo, bot=bot)
    return db, tmp.name, api_server


@pytest.mark.asyncio
async def test_health():
    db, db_path, api_server = _make_fixtures()
    try:
        server = TestServer(api_server.app)
        async with TestClient(server) as client:
            resp = await client.get("/api/health")
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ok"
    finally:
        db.close()
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_notify():
    db, db_path, api_server = _make_fixtures()
    try:
        server = TestServer(api_server.app)
        async with TestClient(server) as client:
            resp = await client.post("/api/notify", json={"message": "テスト通知"})
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "sent"
    finally:
        db.close()
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_notify_missing_message():
    db, db_path, api_server = _make_fixtures()
    try:
        server = TestServer(api_server.app)
        async with TestClient(server) as client:
            resp = await client.post("/api/notify", json={})
            assert resp.status == 400
    finally:
        db.close()
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_schedule():
    db, db_path, api_server = _make_fixtures()
    try:
        server = TestServer(api_server.app)
        async with TestClient(server) as client:
            future = (datetime.now() + timedelta(hours=1)).isoformat()
            resp = await client.post(
                "/api/schedule",
                json={"message": "スケジュールテスト", "scheduled_at": future},
            )
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "scheduled"
            assert "id" in data
    finally:
        db.close()
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_schedule_missing_fields():
    db, db_path, api_server = _make_fixtures()
    try:
        server = TestServer(api_server.app)
        async with TestClient(server) as client:
            resp = await client.post("/api/schedule", json={"message": "テスト"})
            assert resp.status == 400
    finally:
        db.close()
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_list_scheduled():
    db, db_path, api_server = _make_fixtures()
    try:
        server = TestServer(api_server.app)
        async with TestClient(server) as client:
            future = (datetime.now() + timedelta(hours=1)).isoformat()
            await client.post(
                "/api/schedule",
                json={"message": "一覧テスト", "scheduled_at": future},
            )
            resp = await client.get("/api/scheduled")
            assert resp.status == 200
            data = await resp.json()
            assert len(data["notifications"]) >= 1
    finally:
        db.close()
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_cancel_scheduled():
    db, db_path, api_server = _make_fixtures()
    try:
        server = TestServer(api_server.app)
        async with TestClient(server) as client:
            future = (datetime.now() + timedelta(hours=1)).isoformat()
            create_resp = await client.post(
                "/api/schedule",
                json={"message": "キャンセルテスト", "scheduled_at": future},
            )
            create_data = await create_resp.json()
            notif_id = create_data["id"]

            resp = await client.delete(f"/api/scheduled/{notif_id}")
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "cancelled"
    finally:
        db.close()
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_cancel_nonexistent():
    db, db_path, api_server = _make_fixtures()
    try:
        server = TestServer(api_server.app)
        async with TestClient(server) as client:
            resp = await client.delete("/api/scheduled/99999")
            assert resp.status == 404
    finally:
        db.close()
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_notify_invalid_json():
    db, db_path, api_server = _make_fixtures()
    try:
        server = TestServer(api_server.app)
        async with TestClient(server) as client:
            resp = await client.post(
                "/api/notify",
                data="not json",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 400
    finally:
        db.close()
        os.unlink(db_path)
