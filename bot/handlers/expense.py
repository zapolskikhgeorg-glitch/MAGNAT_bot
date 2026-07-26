import re
from decimal import Decimal

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select

from bot.database import get_session
from bot.keyboards import (
    categories_keyboard,
    operation_type_keyboard,
    undo_keyboard,
    back_to_menu_keyboard,
)
from bot.models import Category, Operation, CategoryLimit
from bot.states import AddOperation
from bot.utils import get_or_create_user
from bot.handlers.limits import month_spent, fmt_money

router = Router()

# Ищем число в начале сообщения (целое или с копейками через точку/запятую),
# всё, что после — описание операции.
AMOUNT_PATTERN = re.compile(r"^\s*(\d+(?:[.,]\d{1,2})?)\s*(.*)$")


def parse_amount(text: str) -> tuple[Decimal, str] | None:
    match = AMOUNT_PATTERN.match(text)
    if not match:
        return None
    amount_str = match.group(1).replace(",", ".")
    description = match.group(2).strip()
    try:
        amount = Decimal(amount_str)
    except Exception:
        return None
    if amount <= 0:
        return None
    return amount, description


def _amount_header(amount: Decimal, description: str) -> str:
    """Верхняя строка с суммой и описанием — общая для нескольких экранов."""
    text = f"Сумма: {amount} ₽\n"
    if description:
        text += f"📝 {description}\n"
    return text


@router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def handle_plain_text(message: Message, state: FSMContext) -> None:
    parsed = parse_amount(message.text)
    if parsed is None:
        await message.answer(
            "Не понял сумму 🤔 Напиши число в начале сообщения, например: 350 кофе"
        )
        return

    amount, description = parsed

    await state.update_data(amount=str(amount), description=description)
    await state.set_state(AddOperation.waiting_type)

    text = _amount_header(amount, description) + "\nЭто расход или доход?"
    await message.answer(text, reply_markup=operation_type_keyboard())


@router.callback_query(AddOperation.waiting_type, F.data.startswith("type:"))
async def handle_type_choice(callback: CallbackQuery, state: FSMContext) -> None:
    op_type = callback.data.split(":")[1]  # "expense" или "income"

    data = await state.get_data()
    amount = Decimal(data["amount"])
    description = data["description"]

    async with get_session() as session:
        result = await session.execute(
            select(Category).where(
                Category.type == op_type, Category.is_default == True
            )
        )
        categories = list(result.scalars().all())

    await state.update_data(op_type=op_type)
    await state.set_state(AddOperation.waiting_category)

    type_label = "💰 Доход" if op_type == "income" else "💸 Расход"
    text = _amount_header(amount, description)
    text += f"Тип: {type_label}\n\nВыбери категорию:"

    await callback.message.edit_text(text, reply_markup=categories_keyboard(categories))
    await callback.answer()


@router.callback_query(AddOperation.waiting_category, F.data == "back_to_type")
async def handle_back_to_type(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    amount = Decimal(data["amount"])
    description = data["description"]

    await state.set_state(AddOperation.waiting_type)

    text = _amount_header(amount, description) + "\nЭто расход или доход?"
    await callback.message.edit_text(text, reply_markup=operation_type_keyboard())
    await callback.answer()


@router.callback_query(AddOperation.waiting_category, F.data.startswith("cat:"))
async def handle_category_choice(callback: CallbackQuery, state: FSMContext) -> None:
    category_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    amount = Decimal(data["amount"])
    description = data["description"]
    op_type = data["op_type"]

    async with get_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.first_name or ""
        )
        category = await session.get(Category, category_id)

        operation = Operation(
            user_id=user.id,
            type=op_type,
            amount=amount,
            category_id=category_id,
            raw_text=description,
        )
        session.add(operation)
        await session.commit()
        await session.refresh(operation)

        # Проверяем лимит по категории (только для расходов)
        warning = ""
        if op_type == "expense":
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
                        f"\n\n🔴 Лимит по категории превышен: "
                        f"{fmt_money(spent)} / {fmt_money(limit_amount)} ₽"
                    )
                elif spent >= limit_amount * Decimal("0.8"):
                    warning = (
                        f"\n\n🟡 Близко к лимиту: "
                        f"{fmt_money(spent)} / {fmt_money(limit_amount)} ₽"
                    )

    type_label = "Доход" if op_type == "income" else "Расход"
    text = (
        f"✅ Записано!\n\n"
        f"{type_label}: {amount} ₽\n"
        f"{category.icon} {category.name}"
    )
    if description:
        text += f"\n📝 {description}"
    text += warning

    await callback.message.edit_text(text, reply_markup=undo_keyboard(operation.id))
    await state.clear()
    await callback.answer()


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
