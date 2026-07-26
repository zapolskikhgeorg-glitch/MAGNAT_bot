from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import User


async def get_or_create_user(session: AsyncSession, telegram_id: int, first_name: str) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id, first_name=first_name)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user
