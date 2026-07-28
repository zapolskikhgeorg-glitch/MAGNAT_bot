from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.models import Category


def categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    """Выбор категории расхода при записи траты."""
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=f"{cat.icon} {cat.name}", callback_data=f"cat:{cat.id}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add"))
    return builder.as_markup()


def income_categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    """Выбор категории дохода при записи дохода."""
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=f"{cat.icon} {cat.name}", callback_data=f"inccat:{cat.id}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add"))
    return builder.as_markup()


def undo_keyboard(operation_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="↩️ Отменить запись", callback_data=f"undo:{operation_id}")
    builder.button(text="🏠 Меню", callback_data="menu")
    builder.adjust(1)
    return builder.as_markup()


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню — сгруппировано по частоте использования, 2 кнопки в ряд."""
    builder = InlineKeyboardBuilder()
    # ежедневное
    builder.button(text="📊 Статистика", callback_data="stats")
    builder.button(text="💰 Доход", callback_data="add_income")
    # частое
    builder.button(text="🔍 Поиск", callback_data="search")
    builder.button(text="📂 Категории", callback_data="categories")
    # настройки / периодически
    builder.button(text="🔔 Лимиты", callback_data="limits")
    builder.button(text="📤 Экспорт", callback_data="export")
    # совместное
    builder.button(text="👨‍👩‍👧 Семья", callback_data="family")
    builder.button(text="🧾 Splitwise", callback_data="splitwise")
    builder.adjust(2)
    return builder.as_markup()


def stats_period_keyboard() -> InlineKeyboardMarkup:
    """Периоды статистики + кнопка последних операций + меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Сегодня", callback_data="stats:today")
    builder.button(text="🗓 Неделя", callback_data="stats:week")
    builder.button(text="📆 Месяц", callback_data="stats:month")
    builder.button(text="📝 Последние операции", callback_data="recent")
    builder.button(text="🏠 Меню", callback_data="menu")
    builder.adjust(3, 1, 1)
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Меню", callback_data="menu")
    return builder.as_markup()


def limits_keyboard(has_limits: bool) -> InlineKeyboardMarkup:
    """Экран лимитов: сами лимиты показаны текстом, тут только кнопки действий."""
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить лимит", callback_data="limit_add")
    if has_limits:
        builder.button(text="➖ Удалить лимит", callback_data="limit_del_menu")
    builder.button(text="🏠 Меню", callback_data="menu")
    builder.adjust(1)
    return builder.as_markup()


def limit_delete_keyboard(limits: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    """Режим удаления: каждый лимит = кнопка выбора для удаления."""
    builder = InlineKeyboardBuilder()
    for limit_id, label in limits:
        builder.button(text=f"🗑 {label}", callback_data=f"limit_del:{limit_id}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="limits"))
    return builder.as_markup()


def limit_categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=f"{cat.icon} {cat.name}", callback_data=f"limit_cat:{cat.id}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="limits"))
    return builder.as_markup()


# ===== Экран управления категориями =====

def categories_menu_keyboard() -> InlineKeyboardMarkup:
    """Выбор: смотреть/редактировать расходы или доходы."""
    builder = InlineKeyboardBuilder()
    builder.button(text="💸 Расходные", callback_data="cats_list:expense")
    builder.button(text="💰 Доходные", callback_data="cats_list:income")
    builder.button(text="🏠 Меню", callback_data="menu")
    builder.adjust(2, 1)
    return builder.as_markup()


def categories_view_keyboard(categories: list[Category], cat_type: str) -> InlineKeyboardMarkup:
    """Просмотр списка (категории не кликабельны) + Добавить / Удалить / Назад."""
    builder = InlineKeyboardBuilder()
    # Категории показываем как «неактивные» кнопки (нажатие ничего не делает)
    for cat in categories:
        builder.button(text=f"{cat.icon} {cat.name}", callback_data="noop")
    builder.adjust(1)
    row = []
    builder.row(
        InlineKeyboardButton(text="➕ Добавить", callback_data=f"cat_add:{cat_type}"),
    )
    if categories:
        builder.row(
            InlineKeyboardButton(text="➖ Удалить", callback_data=f"cats_del_menu:{cat_type}"),
        )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="categories"),
    )
    return builder.as_markup()


def categories_delete_keyboard(categories: list[Category], cat_type: str) -> InlineKeyboardMarkup:
    """Режим удаления: каждая категория = кнопка удаления."""
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(
            text=f"🗑 {cat.icon} {cat.name}",
            callback_data=f"cat_del:{cat.id}",
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data=f"cats_list:{cat_type}"),
    )
    return builder.as_markup()


# ===== Семейный бюджет =====

def family_menu_no_family_keyboard() -> InlineKeyboardMarkup:
    """Экран семьи, когда пользователь ещё не в семье."""
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать семейный бюджет", callback_data="family_create")
    builder.button(text="🏠 Меню", callback_data="menu")
    builder.adjust(1)
    return builder.as_markup()


def family_menu_keyboard() -> InlineKeyboardMarkup:
    """Экран семьи, когда пользователь уже состоит в семье."""
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 Участники", callback_data="family_members")
    builder.button(text="➕ Пригласить участника", callback_data="family_invite")
    builder.button(text="🚪 Выйти из семьи", callback_data="family_leave")
    builder.button(text="🏠 Меню", callback_data="menu")
    builder.adjust(1)
    return builder.as_markup()


def family_invite_accept_keyboard(code: str) -> InlineKeyboardMarkup:
    """Кнопки при переходе по ссылке-приглашению."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Принять приглашение", callback_data=f"family_accept:{code}")
    builder.button(text="❌ Отклонить", callback_data="family_decline")
    builder.adjust(1)
    return builder.as_markup()


def family_leave_confirm_keyboard() -> InlineKeyboardMarkup:
    """Подтверждение выхода из семьи."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🚪 Да, выйти", callback_data="family_leave_confirm")
    builder.button(text="◀️ Назад", callback_data="family")
    builder.adjust(1)
    return builder.as_markup()
