from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from bot.config import DATABASE_URL
from bot.models import Base, Category, DEFAULT_EXPENSE_CATEGORIES, DEFAULT_INCOME_CATEGORIES

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Создаёт таблицы (если их ещё нет) и базовые категории."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        result = await session.execute(select(Category).limit(1))
        if result.scalar_one_or_none() is None:
            for name, icon in DEFAULT_EXPENSE_CATEGORIES:
                session.add(Category(name=name, icon=icon, type="expense", is_default=True))
            for name, icon in DEFAULT_INCOME_CATEGORIES:
                session.add(Category(name=name, icon=icon, type="income", is_default=True))
            await session.commit()


def get_session() -> AsyncSession:
    return async_session()
