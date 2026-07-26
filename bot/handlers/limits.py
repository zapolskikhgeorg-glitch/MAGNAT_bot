from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func

from bot.database import get_session
from bot.keyboards import limits_keyboard, limit_categories_keyboard
from bot.models import Category, Operation, CategoryLimit
from bot.states import AddLimit
from bot.utils import get_or_create_user

router = Router()


def fmt_money(value) -> str:
    """Без копеек: 1250 -> '1 250', 1250.5 -> '1 251'."""
    q = Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{int(q):,}".replace(",", " ")


async def month_spent(session, user_id: int, category_id: int) -> Decimal:
    """Сумма расходов по категории за текущий календарный месяц."""
    first = date.today().replace(day=1)
    result = await session.execute(
        select(func.coalesce(func.sum(Operation.amount), 0)).where(
            Operation.user_id == user_id,
            Operation.category_id == category_id,
            Operation.type == "expense",
            Operation.operation_date >= first,
        )
    )
    return Decimal(str(result.scalar() or 0))


async def _render_limits(session, user_id: int) -> tuple[str, list[tuple[int, str]]]:
    """Готовит текст экрана лимитов и список кнопок (id, подпись)."""
    result = await session.execute(
        select(CategoryLimit, Category)
        .join(Category, CategoryLimit.category_id == Category.id)
        .where(CategoryLimit.user_id == user_id)
    )
    rows = result.all()

    if not rows:
        text = (
            "🔔 Лимиты\n\n"
            "У тебя пока нет лимитов.\n"
            "Лимит помогает держать под контролем траты по категории за месяц."
        )
        return text, []

    text = "🔔 Лимиты за текущий месяц\n\n"
    buttons: list[tuple[int, str]] = []
    for limit, category in rows:
        spent = await month_spent(session, user_id, category.id)
        limit_amount = Decimal(str(limit.limit_amount))
        if spent >= limit_amount:
            mark = "🔴"
        elif spent >= limit_amount * Decimal("0.8"):
            mark = "🟡"
        else:
            mark = "🟢"
        body = f"{category.icon} {category.name}: {fmt_money(spent)} / {fmt_money(limit_amount)} ₽"
        text += f"{mark} {body}\n"
        buttons.append((limit.id, f"🗑 {body}"))
    text += "\nНажми на лимит, чтобы удалить его."
    return text, buttons


@router.callback_query(F.data == "limits")
async def show_limits(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with get_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.first_name or ""
        )
        text, buttons = await _render_limits(session, user.id)
    await callback.message.edit_text(text, reply_markup=limits_keyboard(buttons))
    await callback.answer()


@router.callback_query(F.data == "limit_add")
async def limit_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    async with get_session() as session:
        result = await session.execute(
            select(Category).where(
                Category.type == "expense", Category.is_default == True
            )
        )
        categories = list(result.scalars().all())
    await callback.message.edit_text(
        "На какую категорию поставить лимит?",
        reply_markup=limit_categories_keyboard(categories),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("limit_cat:"))
async def limit_pick_category(callback: CallbackQuery, state: FSMContext) -> None:
    category_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        category = await session.get(Category, category_id)
    await state.update_data(limit_category_id=category_id)
    await state.set_state(AddLimit.waiting_amount)
    await callback.message.edit_text(
        f"Категория: {category.icon} {category.name}\n\n"
        f"Введи сумму лимита на месяц (например: 5000)"
    )
    await callback.answer()


@router.message(AddLimit.waiting_amount, F.text, ~F.text.startswith("/"))
async def limit_save(message: Message, state: FSMContext) -> None:
    raw = message.text.replace(" ", "").replace(",", ".")
    try:
        amount = Decimal(raw)
    except Exception:
        amount = Decimal("-1")
    if amount <= 0:
        await message.answer("Не понял сумму 🤔 Введи число, например: 5000")
        return

    data = await state.get_data()
    category_id = int(data["limit_category_id"])

    async with get_session() as session:
        user = await get_or_create_user(
            session, message.from_user.id, message.from_user.first_name or ""
        )
        result = await session.execute(
            select(CategoryLimit).where(
                CategoryLimit.user_id == user.id,
                CategoryLimit.category_id == category_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.limit_amount = amount
        else:
            session.add(
                CategoryLimit(user_id=user.id, category_id=category_id, limit_amount=amount)
            )
        await session.commit()
        text, buttons = await _render_limits(session, user.id)

    await state.clear()
    await message.answer(text, reply_markup=limits_keyboard(buttons))


@router.callback_query(F.data.startswith("limit_del:"))
async def limit_delete(callback: CallbackQuery, state: FSMContext) -> None:
    limit_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.first_name or ""
        )
        limit = await session.get(CategoryLimit, limit_id)
        if limit is not None and limit.user_id == user.id:
            await session.delete(limit)
            await session.commit()
        text, buttons = await _render_limits(session, user.id)
    await callback.message.edit_text(text, reply_markup=limits_keyboard(buttons))
    await callback.answer("Лимит удалён")
