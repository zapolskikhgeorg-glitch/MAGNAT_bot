from aiogram import Router
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from bot.database import get_session
from bot.keyboards import main_menu_keyboard, family_invite_accept_keyboard
from bot.models import User, Family, Trip
from bot.handlers.menu import send_anchor

router = Router()

WELCOME_TEXT = (
    "👋 Привет! Я — <b>MAGNAT</b>, помогаю вести деньги без таблиц.\n\n"
    "Записать расход — просто пришли сумму:\n"
    "   <code>350</code>   или   <code>350 кофе</code>\n\n"
    "💰 Доход и всё остальное — в меню ниже 👇"
)


def _trip_accept_kb(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"trip_accept:{code}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data="trip_decline")],
    ])


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject) -> None:
    await state.clear()
    try:
        await message.delete()  # убираем команду «/start» из чата
    except Exception:
        pass

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

    payload = command.args or ""

    # --- Приглашение в семью (inv_) ---
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

    # --- Приглашение в поездку Splitwise (spl_) ---
    if payload.startswith("spl_"):
        code = payload[4:]
        async with get_session() as session:
            trip_result = await session.execute(
                select(Trip).where(Trip.invite_code == code)
            )
            trip = trip_result.scalar_one_or_none()
        if trip is None:
            await message.answer(
                "❌ Приглашение в поездку недействительно или устарело.",
                reply_markup=main_menu_keyboard(),
            )
            return
        if trip.is_archived:
            await message.answer(
                "Эта поездка уже закрыта (в архиве).",
                reply_markup=main_menu_keyboard(),
            )
            return
        await message.answer(
            f"🧾 Тебя приглашают в поездку «{trip.name}»!\n\n"
            "Расходы будете считать вместе, а бот покажет, кто кому сколько должен.",
            reply_markup=_trip_accept_kb(code),
        )
        return

    # --- Обычный старт (приветствие держим как одно живое сообщение) ---
    await send_anchor(message, WELCOME_TEXT, main_menu_keyboard(), parse_mode="HTML")
