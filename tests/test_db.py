import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from relay.models import User


async def test_create_user(db_session: AsyncSession) -> None:
    user = User(email="ada@example.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    assert user.id is not None
    assert user.is_active is True
    assert user.created_at is not None


async def test_each_test_starts_empty(db_session: AsyncSession) -> None:
    count = await db_session.scalar(select(func.count()).select_from(User))
    assert count == 0


async def test_email_is_unique(db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            User(email="ada@example.com", password_hash="x"),
            User(email="ada@example.com", password_hash="y"),
        ]
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
