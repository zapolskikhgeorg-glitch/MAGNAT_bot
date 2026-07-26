from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import select

from bot.database import get_session
from bot.keyboards import main_menu_keyboard
from bot.models import User

router = Router()

WELCOME_TEXT = (
    "👋 Привет! Я помогу отслеживать доходы и расходы.\n\n"
    "Просто отправь сумму и (по желанию) описание:\n"
    "• 450\n"
    "• 1200 продукты в Пятёрочке\n"
    "• 350,50 кофе\n"
    "• 50000 зарплата\n\n"
    "Я сам пойму, доход это или расход, и предложу категорию.\n\n"
    "Или воспользуйся меню:"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
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

    await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())
