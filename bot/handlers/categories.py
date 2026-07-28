from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, update, delete, or_

from bot.database import get_session
from bot.keyboards import (
    categories_menu_keyboard,
    categories_view_keyboard,
    back_to_menu_keyboard,
)
from bot.models import Category, Operation, HiddenCategory
from bot.states import AddCategory
from bot.utils import get_or_create_user

router = Router()

TYPE_LABEL = {"expense": "💸 Расходные", "income": "💰 Доходные"}


async def _hidden_ids(session, user_id: int) -> list[int]:
    result = await session.execute(
        select(HiddenCategory.category_id).where(HiddenCategory.user_id == user_id)
    )
    return [row[0] for row in result.all()]


async def _load(session, user_id: int, cat_type: str) -> list[Category]:
    """Стандартные + личные категории пользователя, кроме скрытых им."""
    hidden = await _hidden_ids(session, user_id)
    query = select(Category).where(
        Category.type == cat_type,
        or_(Category.is_default == True, Category.user_id == user_id),
    )
    if hidden:
        query = query.where(Category.id.notin_(hidden))
    query = query.order_by(Category.is_default.desc(), Category.id)
    result = await session.execute(query)
    return list(result.scalars().all())


async def _has_hidden(session, user_id: int, cat_type: str) -> bool:
    result = await session.execute(
        select(HiddenCategory.id)
        .join(Category, HiddenCategory.category_id == Category.id)
        .where(HiddenCategory.user_id == user_id, Category.type == cat_type)
        .limit(1)
    )
    return result.first() is not None


def _delete_kb(categories, cat_type: str, has_hidden: bool):
    """Режим удаления: любая категория (своя или стандартная) = кнопка."""
    b = InlineKeyboardBuilder()
    for cat in categories:
        b.button(text=f"🗑 {cat.icon} {cat.name}", callback_data=f"cat_del:{cat.id}")
    b.adjust(1)
    if has_hidden:
        b.row(InlineKeyboardButton(text="♻️ Вернуть стандартные", callback_data=f"cats_restore:{cat_type}"))
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data=f"cats_list:{cat_type}"))
    return b.as_markup()


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "categories")
async def categories_root(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "📂 Категории\n\nКакие категории показать?",
        reply_markup=categories_menu_keyboard(),
    )
    await callback.answer()


async def _show_view(callback: CallbackQuery, cat_type: str) -> None:
    async with get_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.first_name or ""
        )
        categories = await _load(session, user.id, cat_type)
    label = TYPE_LABEL[cat_type]
    if categories:
        text = (
            f"{label} категории\n\n"
            f"Ниже — твой список.\n"
            f"➕ Добавить — создать новую\n"
            f"➖ Удалить — убрать любую (в т.ч. стандартную)"
        )
    else:
        text = f"{label} категории\n\nСписок пуст. Добавь свою или верни стандартные!"
    await callback.message.edit_text(
        text, reply_markup=categories_view_keyboard(categories, cat_type)
    )


@router.callback_query(F.data.startswith("cats_list:"))
async def show_categories(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    cat_type = callback.data.split(":")[1]
    await _show_view(callback, cat_type)
    await callback.answer()


@router.callback_query(F.data.startswith("cats_del_menu:"))
async def delete_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    cat_type = callback.data.split(":")[1]
    async with get_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.first_name or ""
        )
        categories = await _load(session, user.id, cat_type)
        has_hidden = await _has_hidden(session, user.id, cat_type)
    label = TYPE_LABEL[cat_type]
    if not categories:
        await callback.message.edit_text(
            f"{label} — удаление\n\nСписок пуст.",
            reply_markup=_delete_kb([], cat_type, has_hidden),
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        f"{label} — удаление\n\nНажми на категорию, чтобы убрать её из своего списка.",
        reply_markup=_delete_kb(categories, cat_type, has_hidden),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cat_del:"))
async def delete_category(callback: CallbackQuery) -> None:
    category_id = int(callback.data.split(":")[1])

    async with get_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.first_name or ""
        )
        category = await session.get(Category, category_id)
        if category is None:
            await callback.answer("Категория не найдена")
            return
        cat_type = category.type

        if category.is_default:
            # Стандартную не удаляем из базы (она общая) — прячем только у этого пользователя.
            exists = await session.execute(
                select(HiddenCategory).where(
                    HiddenCategory.user_id == user.id,
                    HiddenCategory.category_id == category_id,
                )
            )
            if exists.scalar_one_or_none() is None:
                session.add(HiddenCategory(user_id=user.id, category_id=category_id))
                await session.commit()
        elif category.user_id == user.id:
            # Свою категорию удаляем по-настоящему, операции сохраняем (обнуляем ссылку).
            await session.execute(
                update(Operation)
                .where(Operation.category_id == category_id)
                .values(category_id=None)
            )
            await session.delete(category)
            await session.commit()
        else:
            await callback.answer("Эту категорию убрать нельзя", show_alert=True)
            return

        categories = await _load(session, user.id, cat_type)
        has_hidden = await _has_hidden(session, user.id, cat_type)

    label = TYPE_LABEL[cat_type]
    if categories or has_hidden:
        await callback.message.edit_text(
            f"{label} — удаление\n\nНажми на категорию, чтобы убрать её из своего списка.",
            reply_markup=_delete_kb(categories, cat_type, has_hidden),
        )
    else:
        await callback.message.edit_text(
            f"{label} категории\n\nСписок пуст. Добавь свою!",
            reply_markup=categories_view_keyboard([], cat_type),
        )
    await callback.answer("Убрано")


@router.callback_query(F.data.startswith("cats_restore:"))
async def restore_defaults(callback: CallbackQuery) -> None:
    cat_type = callback.data.split(":")[1]
    async with get_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.first_name or ""
        )
        # Убираем из скрытых все стандартные категории этого типа.
        hidden_rows = await session.execute(
            select(HiddenCategory.id)
            .join(Category, HiddenCategory.category_id == Category.id)
            .where(HiddenCategory.user_id == user.id, Category.type == cat_type)
        )
        ids = [row[0] for row in hidden_rows.all()]
        if ids:
            await session.execute(
                delete(HiddenCategory).where(HiddenCategory.id.in_(ids))
            )
            await session.commit()
        categories = await _load(session, user.id, cat_type)

    label = TYPE_LABEL[cat_type]
    await callback.message.edit_text(
        f"♻️ Стандартные категории возвращены.\n\n{label} категории:",
        reply_markup=categories_view_keyboard(categories, cat_type),
    )
    await callback.answer("Готово")


@router.callback_query(F.data.startswith("cat_add:"))
async def add_category_start(callback: CallbackQuery, state: FSMContext) -> None:
    cat_type = callback.data.split(":")[1]
    await state.update_data(new_cat_type=cat_type)
    await state.set_state(AddCategory.waiting_name)

    label = TYPE_LABEL[cat_type]
    await callback.message.edit_text(
        f"➕ Новая {label.lower()} категория\n\n"
        f"Отправь название. Можно с эмодзи в начале, например:\n"
        f"🎮 Игры\n"
        f"или просто: Подписки",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@router.message(AddCategory.waiting_name, F.text, ~F.text.startswith("/"))
async def add_category_save(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    if not raw:
        await message.answer("Название пустое 🤔 Отправь текст.")
        return
    if len(raw) > 40:
        await message.answer("Слишком длинно 🤔 До 40 символов.")
        return

    data = await state.get_data()
    cat_type = data["new_cat_type"]

    parts = raw.split(maxsplit=1)
    if len(parts) == 2 and not parts[0][0].isalnum():
        icon = parts[0]
        name = parts[1].strip()
    else:
        icon = "📁"
        name = raw

    async with get_session() as session:
        user = await get_or_create_user(
            session, message.from_user.id, message.from_user.first_name or ""
        )
        session.add(
            Category(
                name=name, icon=icon, type=cat_type,
                is_default=False, user_id=user.id,
            )
        )
        await session.commit()
        categories = await _load(session, user.id, cat_type)

    await state.clear()
    label = TYPE_LABEL[cat_type]
    await message.answer(
        f"✅ Категория добавлена!\n\n{label} категории:",
        reply_markup=categories_view_keyboard(categories, cat_type),
    )
