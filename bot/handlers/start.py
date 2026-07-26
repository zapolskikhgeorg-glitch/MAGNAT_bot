from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy import select

from bot.database import get_session
from bot.models import User

router = Router()

WELCOME_TEXT = (
    "👋 Привет! Я помогу отслеживать доходы и расходы.\n\n"
    "Просто отправь сумму и (по желанию) описание:\n"
    "• 450\n"
    "• 1200 продукты в Пятёрочке\n"
    "• 350,50 кофе\n"
    "• 50000 зарплата\n\n"
    "Я сам пойму, доход это или расход, и предложу категорию."
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                telegram_id=message.from_user.id,
                first_name=message.from_user.first_name or "",
            )
            session.add(user)
            await session.commit()

    await message.answer(WELCOME_TEXT)
