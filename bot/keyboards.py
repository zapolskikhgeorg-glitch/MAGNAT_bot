from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.models import Category


def categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    """Клавиатура выбора категории расхода: 2 в ряд + отмена."""
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=f"{cat.icon} {cat.name}", callback_data=f"cat:{cat.id}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add"))
    return builder.as_markup()


def income_categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    """Клавиатура выбора категории дохода."""
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=f"{cat.icon} {cat.name}", callback_data=f"inccat:{cat.id}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add"))
    return builder.as_markup()


def undo_keyboard(operation_id: int) -> InlineKeyboardMarkup:
    """Кнопки под записанной операцией."""
    builder = InlineKeyboardBuilder()
    builder.button(text="↩️ Отменить запись", callback_data=f"undo:{operation_id}")
    builder.button(text="🏠 Меню", callback_data="menu")
    builder.adjust(1)
    return builder.as_markup()


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню бота — полный набор, по 2 в ряд."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="stats")
    builder.button(text="📝 Последние", callback_data="recent")
    builder.button(text="💰 Доход", callback_data="add_income")
    builder.button(text="🔔 Лимиты", callback_data="limits")
    builder.button(text="📤 Экспорт", callback_data="export")
    builder.button(text="🔍 Поиск", callback_data="search")
    builder.button(text="👨‍👩‍👧 Семья", callback_data="family")
    builder.button(text="🧾 Splitwise", callback_data="splitwise")
    builder.adjust(2)
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
