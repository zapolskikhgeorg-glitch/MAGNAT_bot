import io
from datetime import datetime

from aiogram import Router, F
from aiogram.types import CallbackQuery, BufferedInputFile
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from sqlalchemy import select

from bot.database import get_session
from bot.keyboards import back_to_menu_keyboard
from bot.models import Category, Operation, User

router = Router()

TYPE_LABEL = {"expense": "Расход", "income": "Доход"}


@router.callback_query(F.data == "export")
async def export_data(callback: CallbackQuery) -> None:
    await callback.answer("Готовлю файл…")

    async with get_session() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = user_result.scalar_one_or_none()

        if user is None:
            await callback.message.edit_text(
                "📤 Экспорт\n\nПока нет ни одной операции.\n"
                "Напиши сумму, чтобы записать первую!",
                reply_markup=back_to_menu_keyboard(),
            )
            return

        result = await session.execute(
            select(Operation, Category)
            .outerjoin(Category, Operation.category_id == Category.id)
            .where(Operation.user_id == user.id)
            .order_by(Operation.operation_date.desc(), Operation.created_at.desc())
        )
        rows = result.all()

    if not rows:
        await callback.message.edit_text(
            "📤 Экспорт\n\nПока нет ни одной операции.\n"
            "Напиши сумму, чтобы записать первую!",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    # Создаём Excel-книгу.
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Операции"

    headers = ["Дата", "Тип", "Сумма (₽)", "Категория", "Описание"]
    sheet.append(headers)

    # Стиль шапки.
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="4CAF50")
    for cell in sheet[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    total_expense = 0.0
    total_income = 0.0

    for operation, category in rows:
        # amount приходит как Decimal -> приводим к float.
        amount = float(operation.amount)
        cat_label = f"{category.icon} {category.name}" if category else "—"
        sheet.append([
            operation.operation_date.strftime("%d.%m.%Y"),
            TYPE_LABEL.get(operation.type, operation.type),
            round(amount, 2),
            cat_label,
            operation.raw_text or "",
        ])
        if operation.type == "expense":
            total_expense += amount
        else:
            total_income += amount

    # Пустая строка + итоги.
    sheet.append([])
    sheet.append(["", "Итого расходов", round(total_expense, 2)])
    sheet.append(["", "Итого доходов", round(total_income, 2)])
    sheet.append(["", "Баланс", round(total_income - total_expense, 2)])

    # Ширина колонок.
    widths = [14, 10, 14, 22, 40]
    for i, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + i)].width = width

    # Сохраняем в память и отправляем.
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    filename = f"operations_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    file = BufferedInputFile(buffer.read(), filename=filename)

    caption = (
        f"📤 Готово! Всего операций: {len(rows)}\n\n"
        f"💸 Расходы: {int(round(total_expense)):,} ₽\n".replace(",", " ")
        + f"💰 Доходы: {int(round(total_income)):,} ₽".replace(",", " ")
    )

    await callback.message.answer_document(
        document=file,
        caption=caption,
        reply_markup=back_to_menu_keyboard(),
    )
