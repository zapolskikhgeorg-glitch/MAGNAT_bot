import re
from decimal import Decimal, ROUND_HALF_UP

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, or_, func

from bot.database import get_session
from bot.keyboards import (
    categories_keyboard,
    income_categories_keyboard,
    undo_keyboard,
    back_to_menu_keyboard,
)
from bot.models import Category, Operation, CategoryLimit, HiddenCategory
from bot.states import AddOperation, AddIncome
from bot.utils import get_or_create_user
from bot.handlers.limits import month_spent, fmt_money

router = Router()

# Число в начале сообщения (целое или с копейками), остальное — описание.
AMOUNT_PATTERN = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(.*)$")


def parse_amount(text: str) -> tuple[int, str] | None:
    """Возвращает (сумма_целое, описание). Копейки округляются по правилам математики."""
    match = AMOUNT_PATTERN.match(text)
    if not match:
        return None
    amount_str = match.group(1).replace(",", ".")
    description = match.group(2).strip()
    try:
        amount = Decimal(amount_str).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except Exception:
        return None
    if amount <= 0:
        return None
    return int(amount), description


async def _load_categories(session, user_id: int, cat_type: str) -> list[Category]:
    """
    Стандартные + личные категории пользователя, кроме скрытых им,
    отсортированные по частоте использования (чаще выбирал — выше).
    """
    hidden_result = await session.execute(
        select(HiddenCategory.category_id).where(HiddenCategory.user_id == user_id)
    )
    hidden = [row[0] for row in hidden_result.all()]

    # Сколько раз пользователь выбирал каждую категорию (за всё время).
    usage_result = await session.execute(
        select(Operation.category_id, func.count(Operation.id))
        .where(Operation.user_id == user_id, Operation.category_id.isnot(None))
        .group_by(Operation.category_id)
    )
    usage = {cat_id: cnt for cat_id, cnt in usage_result.all()}

    query = select(Category).where(
        Category.type == cat_type,
        or_(Category.is_default == True, Category.user_id == user_id),
    )
    if hidden:
        query = query.where(Category.id.notin_(hidden))

    result = await session.execute(query)
    categories = list(result.scalars().all())

    # Сортировка: частота ↓, затем стандартные раньше личных, затем по id.
    categories.sort(
        key=lambda c: (-usage.get(c.id, 0), 0 if c.is_default else 1, c.id)
    )
    return categories


# =========================================================
#  РАСХОД: пишешь сумму → сразу категории расхода
# =========================================================
@router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def handle_plain_text(message: Message, state: FSMContext) -> None:
    parsed = parse_amount(message.text)
    if parsed is None:
        await message.answer(
            "Не понял сумму 🤔 Напиши число в начале сообщения, например: 350 кофе"
        )
        return

    amount, description = parsed

    async with get_session() as session:
        user = await get_or_create_user(
            session, message.from_user.id, message.from_user.first_name or ""
        )
        categories = await _load_categories(session, user.id, "expense")

    await state.update_data(amount=amount, description=description)
    await state.set_state(AddOperation.waiting_category)

    text = f"💸 Расход: {amount} ₽\n"
    if description:
        text += f"📝 {description}\n"
    text += "\nВыбери категорию:"

    await message.answer(text, reply_markup=categories_keyboard(categories))


@router.callback_query(AddOperation.waiting_category, F.data.startswith("cat:"))
async def handle_category_choice(callback: CallbackQuery, state: FSMContext) -> None:
    category_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    amount = int(data["amount"])
    description = data["description"]

    async with get_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.first_name or ""
        )
        category = await session.get(Category, category_id)

        operation = Operation(
            user_id=user.id,
            type="expense",
            amount=amount,
            category_id=category_id,
            raw_text=description,
        )
        session.add(operation)
        await session.commit()
        await session.refresh(operation)

        # Проверка лимита
        warning = ""
        limit_result = await session.execute(
            select(CategoryLimit).where(
                CategoryLimit.user_id == user.id,
                CategoryLimit.category_id == category_id,
            )
        )
        limit = limit_result.scalar_one_or_none()
        if limit is not None:
            spent = await month_spent(session, user.id, category_id)
            limit_amount = Decimal(str(limit.limit_amount))
            if spent >= limit_amount:
                warning = (
                    f"\n\n🔴 Лимит превышен: "
                    f"{fmt_money(spent)} / {fmt_money(limit_amount)} ₽"
                )
            elif spent >= limit_amount * Decimal("0.8"):
                warning = (
                    f"\n\n🟡 Близко к лимиту: "
                    f"{fmt_money(spent)} / {fmt_money(limit_amount)} ₽"
                )

    text = (
        f"✅ Записано!\n\n"
        f"Расход: {amount} ₽\n"
        f"{category.icon} {category.name}"
    )
    if description:
        text += f"\n📝 {description}"
    text += warning

    await callback.message.edit_text(text, reply_markup=undo_keyboard(operation.id))
    await state.clear()
    await callback.answer()


# =========================================================
#  ДОХОД: кнопка на главной → ввод суммы → категория дохода
# =========================================================
@router.callback_query(F.data == "add_income")
async def income_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddIncome.waiting_amount)
    await callback.message.edit_text(
        "💰 Доход\n\nВведи сумму дохода (можно с описанием):\n"
        "например: 50000 зарплата",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@router.message(AddIncome.waiting_amount, F.text, ~F.text.startswith("/"))
async def income_amount(message: Message, state: FSMContext) -> None:
    parsed = parse_amount(message.text)
    if parsed is None:
        await message.answer(
            "Не понял сумму 🤔 Напиши число, например: 50000 зарплата"
        )
        return

    amount, description = parsed

    async with get_session() as session:
        user = await get_or_create_user(
            session, message.from_user.id, message.from_user.first_name or ""
        )
        categories = await _load_categories(session, user.id, "income")

    await state.update_data(amount=amount, description=description)
    await state.set_state(AddIncome.waiting_category)

    text = f"💰 Доход: {amount} ₽\n"
    if description:
        text += f"📝 {description}\n"
    text += "\nВыбери категорию:"

    await message.answer(text, reply_markup=income_categories_keyboard(categories))


@router.callback_query(AddIncome.waiting_category, F.data.startswith("inccat:"))
async def income_category_choice(callback: CallbackQuery, state: FSMContext) -> None:
    category_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    amount = int(data["amount"])
    description = data["description"]

    async with get_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.first_name or ""
        )
        category = await session.get(Category, category_id)

        operation = Operation(
            user_id=user.id,
            type="income",
            amount=amount,
            category_id=category_id,
            raw_text=description,
        )
        session.add(operation)
        await session.commit()
        await session.refresh(operation)

    text = (
        f"✅ Записано!\n\n"
        f"Доход: {amount} ₽\n"
        f"{category.icon} {category.name}"
    )
    if description:
        text += f"\n📝 {description}"

    await callback.message.edit_text(text, reply_markup=undo_keyboard(operation.id))
    await state.clear()
    await callback.answer()


# =========================================================
#  Общие: отмена, отмена записи
# =========================================================
@router.callback_query(F.data == "cancel_add")
async def handle_cancel_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "Добавление отменено.", reply_markup=back_to_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("undo:"))
async def handle_undo(callback: CallbackQuery) -> None:
    operation_id = int(callback.data.split(":")[1])

    async with get_session() as session:
        operation = await session.get(Operation, operation_id)
        if operation is not None:
            await session.delete(operation)
            await session.commit()

    await callback.message.edit_text(
        "↩️ Запись отменена.", reply_markup=back_to_menu_keyboard()
    )
    await callback.answer()
