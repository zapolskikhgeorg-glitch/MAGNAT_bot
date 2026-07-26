from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func, or_

from bot.database import get_session
from bot.keyboards import back_to_menu_keyboard
from bot.models import Category, Operation, User
from bot.states import Search

router = Router()


def format_money(value) -> str:
    return f"{int(round(value)):,}".replace(",", " ") + " ₽"


@router.callback_query(F.data == "search")
async def search_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Search.waiting_query)
    await callback.message.edit_text(
        "🔍 Поиск операций\n\n"
        "Напиши, что ищем:\n"
        "• слово — например «кофе» или «такси»\n"
        "• сумму — например «500»\n\n"
        "Ищу и по описанию, и по названию категории.",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@router.message(Search.waiting_query, F.text, ~F.text.startswith("/"))
async def search_run(message: Message, state: FSMContext) -> None:
    query = message.text.strip()
    if not query:
        await message.answer("Пустой запрос 🤔 Напиши слово или сумму.")
        return

    await state.clear()

    async with get_session() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = user_result.scalar_one_or_none()

        if user is None:
            await message.answer(
                "Пока нет ни одной операции. Напиши сумму, чтобы начать!",
                reply_markup=back_to_menu_keyboard(),
            )
            return

        # Условия поиска: по тексту описания или названию категории.
        pattern = f"%{query.lower()}%"
        conditions = [
            func.lower(Operation.raw_text).like(pattern),
            func.lower(Category.name).like(pattern),
        ]

        # Если запрос — число, ищем ещё и по сумме (±5%).
        amount_value = _parse_amount(query)
        if amount_value is not None:
            delta = max(amount_value * 0.05, 1)
            conditions.append(
                Operation.amount.between(amount_value - delta, amount_value + delta)
            )

        result = await session.execute(
            select(Operation, Category)
            .outerjoin(Category, Operation.category_id == Category.id)
            .where(Operation.user_id == user.id, or_(*conditions))
            .order_by(Operation.created_at.desc())
            .limit(20)
        )
        rows = result.all()

    if not rows:
        await message.answer(
            f"По запросу «{query}» ничего не найдено 🤷\n\n"
            f"Попробуй другое слово или сумму.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    total = sum(op.amount for op, _ in rows if op.type == "expense")
    lines = [f"🔍 Найдено по запросу «{query}»:", ""]
    for operation, category in rows:
        sign = "−" if operation.type == "expense" else "+"
        cat_label = f"{category.icon} {category.name}" if category else "без категории"
        day = operation.operation_date.strftime("%d.%m")
        line = f"{day}  {sign}{format_money(operation.amount)}  {cat_label}"
        if operation.raw_text:
            line += f" — {operation.raw_text}"
        lines.append(line)

    lines.append("")
    lines.append(f"💸 Сумма расходов в найденном: {format_money(total)}")
    if len(rows) == 20:
        lines.append("(показаны первые 20 — уточни запрос, если нужно точнее)")

    await message.answer("\n".join(lines), reply_markup=back_to_menu_keyboard())


def _parse_amount(text: str) -> float | None:
    """Пробуем понять, число ли это. '500', '1 500', '1500,50' — да."""
    cleaned = text.replace(" ", "").replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if value <= 0:
        return None
    return value
