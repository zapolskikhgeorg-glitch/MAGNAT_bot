from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, update, or_

from bot.database import get_session
from bot.keyboards import (
    categories_menu_keyboard,
    categories_view_keyboard,
    categories_delete_keyboard,
    back_to_menu_keyboard,
)
from bot.models import Category, Operation
from bot.states import AddCategory
from bot.utils import get_or_create_user

router = Router()

TYPE_LABEL = {"expense": "💸 Расходные", "income": "💰 Доходные"}


async def _load(user_id: int, cat_type: str) -> list[Category]:
    """Стандартные категории + личные категории этого пользователя."""
    async with get_session() as session:
        result = await session.execute(
            select(Category)
            .where(
                Category.type == cat_type,
                or_(
                    Category.is_default == True,
                    Category.user_id == user_id,
                ),
            )
            .order_by(Category.is_default.desc(), Category.id)
        )
        return list(result.scalars().all())


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    """Нажатие на категорию в режиме просмотра — ничего не делаем."""
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
        user_id = user.id
    categories = await _load(user_id, cat_type)
    label = TYPE_LABEL[cat_type]
    if categories:
        text = (
            f"{label} категории\n\n"
            f"Ниже — твои категории.\n"
            f"➕ Добавить — создать новую\n"
            f"➖ Удалить — убрать существующую"
        )
    else:
        text = f"{label} категории\n\nПока нет ни одной. Добавь первую!"
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
        user_id = user.id
    categories = await _load(user_id, cat_type)
    # Удалять можно только свои категории (стандартные не трогаем)
    own = [c for c in categories if not c.is_default]
    label = TYPE_LABEL[cat_type]
    if not own:
        await callback.message.edit_text(
            f"{label} — удаление\n\nУ тебя нет своих категорий для удаления "
            f"(стандартные удалять нельзя).",
            reply_markup=categories_view_keyboard(categories, cat_type),
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        f"{label} — удаление\n\nНажми на категорию, чтобы удалить её.",
        reply_markup=categories_delete_keyboard(own, cat_type),
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
        # Защита: нельзя удалить стандартную или чужую категорию
        if category.is_default or category.user_id != user.id:
            await callback.answer("Эту категорию удалить нельзя", show_alert=True)
            return
        cat_type = category.type

        # Операции с этой категорией сохраняем — просто обнуляем ссылку.
        await session.execute(
            update(Operation)
            .where(Operation.category_id == category_id)
            .values(category_id=None)
        )
        await session.delete(category)
        await session.commit()
        user_id = user.id

    categories = await _load(user_id, cat_type)
    own = [c for c in categories if not c.is_default]
    label = TYPE_LABEL[cat_type]
    if own:
        await callback.message.edit_text(
            f"{label} — удаление\n\nНажми на категорию, чтобы удалить её.",
            reply_markup=categories_delete_keyboard(own, cat_type),
        )
    else:
        await callback.message.edit_text(
            f"{label} категории\n\nСвоих категорий не осталось. Добавь новую!",
            reply_markup=categories_view_keyboard(categories, cat_type),
        )
    await callback.answer("Категория удалена")


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
                name=name,
                icon=icon,
                type=cat_type,
                is_default=False,
                user_id=user.id,
            )
        )
        await session.commit()
        user_id = user.id

    categories = await _load(user_id, cat_type)
    await state.clear()

    label = TYPE_LABEL[cat_type]
    await message.answer(
        f"✅ Категория добавлена!\n\n{label} категории:",
        reply_markup=categories_view_keyboard(categories, cat_type),
    )
