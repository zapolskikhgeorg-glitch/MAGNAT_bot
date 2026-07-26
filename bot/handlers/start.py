from aiogram import Router
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import select

from bot.database import get_session
from bot.keyboards import main_menu_keyboard, family_invite_accept_keyboard
from bot.models import User, Family

router = Router()

WELCOME_TEXT = (
    "👋 Привет! Я помогу вести учёт расходов и доходов.\n\n"
    "💸 <b>Расход</b> — просто напиши сумму и (по желанию) описание:\n"
    "• 450\n"
    "• 1200 продукты в Пятёрочке\n"
    "• 350 кофе\n"
    "После суммы выберешь категорию.\n\n"
    "💰 <b>Доход</b> — жми кнопку «Доход» в меню.\n\n"
    "Копейки округляю до целого рубля. Пользуйся меню:"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject) -> None:
    await state.clear()

    # Регистрируем пользователя (если ещё нет)
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
        current_family_id = user.family_id

    # Проверяем: пришёл ли пользователь по ссылке-приглашению вида inv_XXXX
    payload = command.args or ""
    if payload.startswith("inv_"):
        code = payload[4:]
        async with get_session() as session:
            fam_result = await session.execute(
                select(Family).where(Family.invite_code == code)
            )
            fam = fam_result.scalar_one_or_none()

            if fam is None:
                await message.answer(
                    "❌ Приглашение недействительно или устарело.",
                    reply_markup=main_menu_keyboard(),
                )
                return

            if current_family_id == fam.id:
                await message.answer(
                    "Ты уже состоишь в этой семье 🙂",
                    reply_markup=main_menu_keyboard(),
                )
                return

            owner = await session.get(User, fam.owner_id)
            owner_name = (owner.first_name if owner and owner.first_name else "пользователь")

        await message.answer(
            f"👨‍👩‍👧 Тебя приглашают в семейный бюджет!\n\n"
            f"Создатель: <b>{owner_name}</b>\n\n"
            f"Если примешь — ваши расходы и доходы будут учитываться вместе.",
            reply_markup=family_invite_accept_keyboard(code),
            parse_mode="HTML",
        )
        return

    # Обычный старт
    await message.answer(
        WELCOME_TEXT, reply_markup=main_menu_keyboard(), parse_mode="HTML"
    )
