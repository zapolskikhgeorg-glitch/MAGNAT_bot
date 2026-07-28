import logging
from datetime import date, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func

from bot.database import get_session
from bot.keyboards import (
    main_menu_keyboard,
    stats_period_keyboard,
    back_to_menu_keyboard,
)
from bot.models import Category, Operation, User

router = Router()

MENU_TEXT = "🏠 Главное меню\n\nВыбери, что нужно, или просто напиши сумму."

# chat_id -> message_id последнего «живого» сообщения-меню/приветствия.
# Чтобы в чате не копились старые меню: новое приходит — прежнее удаляем.
_last_menu: dict[int, int] = {}


async def send_anchor(message: Message, text: str, reply_markup, parse_mode=None) -> None:
    """Удаляет прежнее живое меню в этом чате и отправляет новое, запоминая его id."""
    chat_id = message.chat.id
    prev = _last_menu.get(chat_id)
    if prev is not None:
        try:
            await message.bot.delete_message(chat_id, prev)
        except Exception:
            pass
    sent = await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    _last_menu[chat_id] = sent.message_id


def format_money(value) -> str:
    return f"{int(round(value)):,}".replace(",", " ") + " ₽"


async def get_scope_user_ids(session, user: User) -> list[int]:
    """
    Возвращает список id пользователей, чьи операции учитываются в статистике.
    Если пользователь в семье — все участники семьи, иначе — только он сам.
    """
    if user.family_id is None:
        return [user.id]
    result = await session.execute(
        select(User.id).where(User.family_id == user.family_id)
    )
    return [row[0] for row in result.all()]


def _op_line(operation, category) -> str:
    """Одна строка операции для текста списка."""
    sign = "−" if operation.type == "expense" else "+"
    cat = f"{category.icon} {category.name}" if category else "без категории"
    day = operation.operation_date.strftime("%d.%m")
    line = f"{day}  {sign}{format_money(operation.amount)}  ·  {cat}"
    if operation.raw_text:
        line += f" — {operation.raw_text}"
    return line


def recent_view_keyboard(has_rows: bool) -> InlineKeyboardMarkup:
    """Экран последних операций: список текстом, тут только кнопки действий."""
    b = InlineKeyboardBuilder()
    if has_rows:
        b.button(text="🗑 Удалить запись", callback_data="op_del_menu")
    b.button(text="🏠 Меню", callback_data="menu")
    b.adjust(1)
    return b.as_markup()


def recent_delete_keyboard(rows) -> InlineKeyboardMarkup:
    """Режим удаления: каждая операция = кнопка выбора."""
    b = InlineKeyboardBuilder()
    for operation, category in rows:
        sign = "−" if operation.type == "expense" else "+"
        cat = f"{category.icon} {category.name}" if category else "без категории"
        day = operation.operation_date.strftime("%d.%m")
        label = f"{day} {sign}{format_money(operation.amount)} · {cat}"
        if operation.raw_text:
            label += f" · {operation.raw_text}"
        b.button(text=label[:64], callback_data=f"op_del:{operation.id}")
    b.adjust(1)
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data="recent"))
    return b.as_markup()


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    try:
        await message.delete()  # убираем команду «/menu» из чата
    except Exception:
        pass
    await send_anchor(message, MENU_TEXT, main_menu_keyboard())


@router.callback_query(F.data == "menu")
async def show_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    msg = callback.message
    chat_id = msg.chat.id

    if msg.text is not None:
        # Обычное текстовое сообщение — редактируем на месте.
        prev = _last_menu.get(chat_id)
        if prev is not None and prev != msg.message_id:
            try:
                await callback.bot.delete_message(chat_id, prev)
            except Exception:
                pass
        await msg.edit_text(MENU_TEXT, reply_markup=main_menu_keyboard())
        _last_menu[chat_id] = msg.message_id
    else:
        # Сообщение с файлом/медиа (например, экспорт) редактировать в текст нельзя —
        # присылаем свежее меню отдельным сообщением, сам файл оставляем.
        await send_anchor(msg, MENU_TEXT, main_menu_keyboard())

    await callback.answer()


@router.callback_query(F.data == "stats")
async def choose_period(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "📊 Статистика\n\nЗа какой период показать?",
        reply_markup=stats_period_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("stats:"))
async def show_stats(callback: CallbackQuery) -> None:
    period = callback.data.split(":")[1]
    today = date.today()

    if period == "today":
        date_from = today
        title = "📅 Сегодня"
    elif period == "week":
        date_from = today - timedelta(days=6)
        title = "🗓 Последние 7 дней"
    else:
        date_from = today - timedelta(days=29)
        title = "📆 Последние 30 дней"

    async with get_session() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = user_result.scalar_one_or_none()

        if user is None:
            await callback.message.edit_text(
                "Пока нет ни одной операции. Напиши сумму, чтобы начать!",
                reply_markup=back_to_menu_keyboard(),
            )
            await callback.answer()
            return

        user_ids = await get_scope_user_ids(session, user)
        is_family = user.family_id is not None

        totals_result = await session.execute(
            select(Operation.type, func.sum(Operation.amount))
            .where(
                Operation.user_id.in_(user_ids),
                Operation.operation_date >= date_from,
                Operation.operation_date <= today,
            )
            .group_by(Operation.type)
        )
        totals = dict(totals_result.all())

        by_person = []
        if is_family:
            person_result = await session.execute(
                select(User.first_name, func.sum(Operation.amount))
                .join(Operation, Operation.user_id == User.id)
                .where(
                    Operation.user_id.in_(user_ids),
                    Operation.type == "expense",
                    Operation.operation_date >= date_from,
                    Operation.operation_date <= today,
                )
                .group_by(User.id, User.first_name)
                .order_by(func.sum(Operation.amount).desc())
            )
            by_person = person_result.all()

        by_category_result = await session.execute(
            select(Category.icon, Category.name, func.sum(Operation.amount))
            .join(Operation, Operation.category_id == Category.id)
            .where(
                Operation.user_id.in_(user_ids),
                Operation.type == "expense",
                Operation.operation_date >= date_from,
                Operation.operation_date <= today,
            )
            .group_by(Category.icon, Category.name)
            .order_by(func.sum(Operation.amount).desc())
        )
        by_category = by_category_result.all()

        income_cat_result = await session.execute(
            select(Category.icon, Category.name, func.sum(Operation.amount))
            .join(Operation, Operation.category_id == Category.id)
            .where(
                Operation.user_id.in_(user_ids),
                Operation.type == "income",
                Operation.operation_date >= date_from,
                Operation.operation_date <= today,
            )
            .group_by(Category.icon, Category.name)
            .order_by(func.sum(Operation.amount).desc())
        )
        by_income = income_cat_result.all()

    expense = totals.get("expense") or 0
    income = totals.get("income") or 0
    balance = income - expense

    lines = [title]
    if is_family:
        lines.append("👨‍👩‍👧 Семейный бюджет")
    lines.append("")

    if is_family and by_person:
        lines.append("👤 Расходы по участникам:")
        for name, amount in by_person:
            lines.append(f"• {name or 'Участник'}: {format_money(amount)}")
        lines.append("")

    lines.append(f"💸 Расходы: {format_money(expense)}")
    lines.append(f"💰 Доходы: {format_money(income)}")
    lines.append(f"⚖️ Баланс: {format_money(balance)}")

    if by_category:
        lines.append("")
        lines.append("📂 Расходы по категориям:")
        for icon, name, amount in by_category:
            share = (amount / expense * 100) if expense else 0
            lines.append(f"{icon} {name}: {format_money(amount)} ({share:.0f}%)")

    if by_income:
        lines.append("")
        lines.append("📥 Доходы по категориям:")
        for icon, name, amount in by_income:
            lines.append(f"{icon} {name}: {format_money(amount)}")

    if not expense and not income:
        lines.append("")
        lines.append("За этот период операций пока нет.")

    await callback.message.edit_text(
        "\n".join(lines), reply_markup=stats_period_keyboard()
    )
    await callback.answer()


async def _get_recent_rows(session, telegram_id: int):
    """(user, rows) — последние 15 операций в области видимости пользователя."""
    user_result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        return None, []
    user_ids = await get_scope_user_ids(session, user)
    result = await session.execute(
        select(Operation, Category)
        .outerjoin(Category, Operation.category_id == Category.id)
        .where(Operation.user_id.in_(user_ids))
        .order_by(Operation.created_at.desc())
        .limit(15)
    )
    return user, result.all()


async def _render_recent(callback: CallbackQuery) -> None:
    """Список операций текстом + кнопки действий."""
    async with get_session() as session:
        user, rows = await _get_recent_rows(session, callback.from_user.id)

    if not rows:
        await callback.message.edit_text(
            "Пока нет ни одной операции. Напиши сумму, чтобы начать!",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    lines = ["📝 Последние операции", ""]
    for operation, category in rows:
        lines.append(_op_line(operation, category))
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=recent_view_keyboard(True)
    )


@router.callback_query(F.data == "recent")
async def show_recent(callback: CallbackQuery) -> None:
    await _render_recent(callback)
    await callback.answer()


@router.callback_query(F.data == "op_del_menu")
async def op_del_menu(callback: CallbackQuery) -> None:
    async with get_session() as session:
        user, rows = await _get_recent_rows(session, callback.from_user.id)

    if not rows:
        await callback.answer("Записей нет", show_alert=True)
        await _render_recent(callback)
        return

    await callback.message.edit_text(
        "Какую запись удалить?", reply_markup=recent_delete_keyboard(rows)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("op_del:"))
async def op_del_confirm(callback: CallbackQuery) -> None:
    op_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        operation = await session.get(Operation, op_id)
        if operation is None:
            await callback.answer("Запись уже удалена", show_alert=True)
            await _render_recent(callback)
            return
        category = (
            await session.get(Category, operation.category_id)
            if operation.category_id else None
        )
        info = _op_line(operation, category)

    b = InlineKeyboardBuilder()
    b.button(text="🗑 Да, удалить", callback_data=f"op_delok:{op_id}")
    b.button(text="◀️ Отмена", callback_data="op_del_menu")
    b.adjust(1)
    await callback.message.edit_text(
        f"🗑 Удалить эту запись?\n\n{info}\n\n"
        "Она исчезнет из списка и вычтется из статистики.",
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("op_delok:"))
async def op_del_do(callback: CallbackQuery) -> None:
    op_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        operation = await session.get(Operation, op_id)
        if operation is not None:
            await session.delete(operation)
            await session.commit()
    await _render_recent(callback)
    await callback.answer("Запись удалена")
