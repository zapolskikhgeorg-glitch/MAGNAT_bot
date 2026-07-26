from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.models import Category


def categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    """Строит клавиатуру 2 кнопки в ряд + кнопка отмены снизу."""
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=f"{cat.icon} {cat.name}", callback_data=f"cat:{cat.id}")
    builder.button(text="❌ Отмена", callback_data="cancel_add")
    builder.adjust(2)
    return builder.as_markup()


def undo_keyboard(operation_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="↩️ Отменить запись", callback_data=f"undo:{operation_id}")
    return builder.as_markup()
