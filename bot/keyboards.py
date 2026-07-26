from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.models import Category


def operation_type_keyboard() -> InlineKeyboardMarkup:
    """Выбор типа операции: расход или доход."""
    builder = InlineKeyboardBuilder()
    builder.button(text="💸 Расход", callback_data="type:expense")
    builder.button(text="💰 Доход", callback_data="type:income")
    builder.button(text="❌ Отмена", callback_data="cancel_add")
    builder.adjust(2, 1)
    return builder.as_markup()


def categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    """Клавиатура выбора категории: 2 кнопки в ряд + назад и отмена снизу."""
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=f"{cat.icon} {cat.name}", callback_data=f"cat:{cat.id}")
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_type"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add"),
    )
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
    builder.button(text="🔔 Лимиты", callback_data="limits")
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


def limits_keyboard(limits: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    """Экран лимитов: каждый лимит — кнопка (нажатие = удалить) + добавить + меню."""
    builder = InlineKeyboardBuilder()
    for limit_id, label in limits:
        builder.button(text=label, callback_data=f"limit_del:{limit_id}")
    builder.button(text="➕ Добавить лимит", callback_data="limit_add")
    builder.button(text="🏠 Меню", callback_data="menu")
    builder.adjust(1)
    return builder.as_markup()


def limit_categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    """Выбор категории расхода для установки лимита."""
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=f"{cat.icon} {cat.name}", callback_data=f"limit_cat:{cat.id}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="limits"))
    return builder.as_markup()
