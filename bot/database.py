from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from bot.config import DATABASE_URL
from bot.models import Base, Category, DEFAULT_EXPENSE_CATEGORIES, DEFAULT_INCOME_CATEGORIES

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def _sync_default_categories(session, defaults, op_type: str) -> None:
    """Добавляет только те базовые категории, которых ещё нет в базе."""
    result = await session.execute(
        select(Category).where(Category.type == op_type, Category.is_default == True)
    )
    existing_names = {c.name for c in result.scalars().all()}
    for name, icon in defaults:
        if name not in existing_names:
            session.add(Category(name=name, icon=icon, type=op_type, is_default=True))


async def init_db() -> None:
    """Создаёт таблицы (если их ещё нет) и досоздаёт недостающие базовые категории."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        await _sync_default_categories(session, DEFAULT_EXPENSE_CATEGORIES, "expense")
        await _sync_default_categories(session, DEFAULT_INCOME_CATEGORIES, "income")
        await session.commit()


def get_session() -> AsyncSession:
    return async_session()
