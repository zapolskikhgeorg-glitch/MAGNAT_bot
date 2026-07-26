import re
from decimal import Decimal

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select

from bot.database import get_session
from bot.keyboards import categories_keyboard, undo_keyboard, back_to_menu_keyboard
from bot.models import Category, Operation
from bot.states import AddOperation
from bot.utils import get_or_create_user

router = Router()

# Ищем число в начале сообщения (целое или с копейками через точку/запятую),
# всё, что после — описание операции.
AMOUNT_PATTERN = re.compile(r"^\s*(\d+(?:[.,]\d{1,2})?)\s*(.*)$")

# Если в описании встречается одно из этих слов — считаем, что это доход,
# а не расход. Список можно будет расширять по мере наблюдений.
INCOME_KEYWORDS = {
    "зарплата", "зп", "доход", "фриланс", "аванс", "премия",
    "подработка", "возврат", "кэшбэк", "продал", "вернул",
    "получил", "гонорар", "выручка",
}


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


def guess_type(description: str) -> str:
    words = set(description.lower().split())
    if words & INCOME_KEYWORDS:
        return "income"
    return "expense"


@router.message(F.text, ~F.text.startswith("/"))
async def handle_plain_text(message: Message, state: FSMContext) -> None:
    parsed = parse_amount(message.text)
    if parsed is None:
        await message.answer(
            "Не понял сумму 🤔 Напиши число в начале сообщения, например: 350 кофе"
        )
        return

    amount, description = parsed
    op_type = guess_type(description)

    async with get_session() as session:
        result = await session.execute(
            select(Category).where(Category.type == op_type, Category.is_default == True)
        )
        categories = list(result.scalars().all())

    await state.update_data(amount=str(amount), description=description, op_type=op_type)
    await state.set_state(AddOperation.waiting_category)

    type_label = "💰 Доход" if op_type == "income" else "💸 Расход"
    text = f"{type_label}: {amount} ₽\n"
    if description:
        text += f"📝 {description}\n"
    text += "\nВыбери категорию:"

    await message.answer(text, reply_markup=categories_keyboard(categories))


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

    type_label = "Доход" if op_type == "income" else "Расход"
    text = (
        f"✅ Записано!\n\n"
        f"{type_label}: {amount} ₽\n"
        f"{category.icon} {category.name}"
    )
    if description:
        text += f"\n📝 {description}"

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
