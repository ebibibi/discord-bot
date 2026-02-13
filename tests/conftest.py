"""共通fixtures"""

import os
import tempfile

import pytest

from src.database.models import Database
from src.database.repository import NotificationRepository


@pytest.fixture
def tmp_db():
    """一時DBを作成するfixture。"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    db = Database(db_path=db_path)
    db.initialize()
    yield db
    db.close()
    os.unlink(db_path)


@pytest.fixture
def repo(tmp_db):
    """NotificationRepositoryのfixture。"""
    return NotificationRepository(tmp_db)
