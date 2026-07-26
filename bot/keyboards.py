from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.models import Category


def categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    """Клавиатура выбора категории: 2 кнопки в ряд + отмена снизу."""
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=f"{cat.icon} {cat.name}", callback_data=f"cat:{cat.id}")
    builder.button(text="❌ Отмена", callback_data="cancel_add")
    builder.adjust(2)
    return builder.as_markup()


def undo_keyboard(operation_id: int) -> InlineKeyboardMarkup:
    """Кнопки под записанной операцией: отменить запись + вернуться в меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text="↩️ Отменить запись", callback_data=f"undo:{operation_id}")
    builder.button(text="🏠 Меню", callback_data="menu")
    builder.adjust(1)
    return builder.as_markup()


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню бота."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="stats")
    builder.button(text="📝 Последние операции", callback_data="recent")
    builder.adjust(1)
    return builder.as_markup()


def stats_period_keyboard() -> InlineKeyboardMarkup:
    """Выбор периода для статистики."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Сегодня", callback_data="stats:today")
    builder.button(text="🗓 Неделя", callback_data="stats:week")
    builder.button(text="📆 Месяц", callback_data="stats:month")
    builder.button(text="🏠 Меню", callback_data="menu")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Одна кнопка возврата в главное меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Меню", callback_data="menu")
    return builder.as_markup()
