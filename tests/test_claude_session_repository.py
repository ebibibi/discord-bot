"""Tests for ClaudeSessionRepository."""

import asyncio
import os
import tempfile

import pytest

from claude_discord.database.models import init_db
from src.database.claude_session_repository import ClaudeSessionRepository, SessionRecord


@pytest.fixture
def db_path():
    """Create a temporary database."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def repo(db_path):
    """Create repository with initialized schema (using bridge's init_db)."""
    asyncio.get_event_loop().run_until_complete(init_db(db_path))
    return ClaudeSessionRepository(db_path)


@pytest.mark.asyncio
async def test_save_and_get(repo):
    record = await repo.save(thread_id=12345, session_id="sess-abc")
    assert record.thread_id == 12345
    assert record.session_id == "sess-abc"

    fetched = await repo.get(12345)
    assert fetched is not None
    assert fetched.session_id == "sess-abc"


@pytest.mark.asyncio
async def test_get_nonexistent(repo):
    result = await repo.get(99999)
    assert result is None


@pytest.mark.asyncio
async def test_save_upsert(repo):
    await repo.save(thread_id=100, session_id="sess-1")
    await repo.save(thread_id=100, session_id="sess-2")

    record = await repo.get(100)
    assert record is not None
    assert record.session_id == "sess-2"


@pytest.mark.asyncio
async def test_delete(repo):
    await repo.save(thread_id=200, session_id="sess-del")
    deleted = await repo.delete(200)
    assert deleted is True

    result = await repo.get(200)
    assert result is None


@pytest.mark.asyncio
async def test_delete_nonexistent(repo):
    deleted = await repo.delete(999)
    assert deleted is False
