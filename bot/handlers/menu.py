from datetime import date, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func

from bot.database import get_session
from bot.keyboards import (
    main_menu_keyboard,
    stats_period_keyboard,
    back_to_menu_keyboard,
)
from bot.models import Category, Operation, User

router = Router()

MENU_TEXT = "🏠 Главное меню\n\nВыбери действие или просто напиши сумму, чтобы записать расход."


def format_money(value) -> str:
    return f"{int(round(value)):,}".replace(",", " ") + " ₽"


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(MENU_TEXT, reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "menu")
async def show_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(MENU_TEXT, reply_markup=main_menu_keyboard())
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

        totals_result = await session.execute(
            select(Operation.type, func.sum(Operation.amount))
            .where(
                Operation.user_id == user.id,
                Operation.operation_date >= date_from,
                Operation.operation_date <= today,
            )
            .group_by(Operation.type)
        )
        totals = dict(totals_result.all())

        by_category_result = await session.execute(
            select(Category.icon, Category.name, func.sum(Operation.amount))
            .join(Operation, Operation.category_id == Category.id)
            .where(
                Operation.user_id == user.id,
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
                Operation.user_id == user.id,
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

    lines = [title, ""]
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


@router.callback_query(F.data == "recent")
async def show_recent(callback: CallbackQuery) -> None:
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

        result = await session.execute(
            select(Operation, Category)
            .outerjoin(Category, Operation.category_id == Category.id)
            .where(Operation.user_id == user.id)
            .order_by(Operation.created_at.desc())
            .limit(10)
        )
        rows = result.all()

    if not rows:
        text = "Пока нет ни одной операции. Напиши сумму, чтобы начать!"
    else:
        lines = ["📝 Последние операции:", ""]
        for operation, category in rows:
            sign = "−" if operation.type == "expense" else "+"
            cat_label = f"{category.icon} {category.name}" if category else "без категории"
            day = operation.operation_date.strftime("%d.%m")
            line = f"{day}  {sign}{format_money(operation.amount)}  {cat_label}"
            if operation.raw_text:
                line += f" — {operation.raw_text}"
            lines.append(line)
        text = "\n".join(lines)

    await callback.message.edit_text(text, reply_markup=stats_period_keyboard())
    await callback.answer()


# ===== Заглушки (сделаем позже) =====
@router.callback_query(F.data == "export")
async def stub_export(callback: CallbackQuery) -> None:
    await callback.answer("🚧 Экспорт скоро появится", show_alert=True)


@router.callback_query(F.data == "family")
async def stub_family(callback: CallbackQuery) -> None:
    await callback.answer("🚧 Семья скоро появится", show_alert=True)


@router.callback_query(F.data == "splitwise")
async def stub_splitwise(callback: CallbackQuery) -> None:
    await callback.answer("🚧 Splitwise скоро появится", show_alert=True)
